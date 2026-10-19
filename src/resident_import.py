"""Upload a resident list (CSV / Excel) into Resident Meal & Consumption Records.

The uploaded file becomes the resident list. Each row is recognised by its Resident ID (the ID from the
facility's own system): new ID -> new resident, known ID -> update room / name / dining area / diet,
Status 'Discharged' -> hidden from the nurse list. Active residents who are not in the file (including the
generated demo residents) are also hidden. Hidden residents keep their meal history and plate-waste records.
Nothing is saved until the preview is confirmed.
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from .db import connection, fetchall
from .textures import parse_texture, texture_label

TEMPLATE_COLUMNS = ["Resident ID", "Name", "Room", "Dining area", "Diet", "Status"]
REQUIRED = ["resident_id", "name", "room", "dining_area"]
ALIASES = {
    "resident_id": ["resident_id", "id", "resident_number", "urn", "mrn"],
    "name": ["name", "resident_name", "full_name"],
    "room": ["room", "room_number", "room_no", "bed"],
    "facility": ["facility", "site", "home"],
    "dining_area": ["dining_area", "service_area", "wing", "unit", "area"],
    "menu_type": ["diet", "menu_type", "menu", "texture", "diet_texture", "menu_variant", "iddsi", "iddsi_level"],
    "status": ["status", "active"],
}
ID_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9\-]{2,24}")


def read_file(uploaded) -> pd.DataFrame:
    name = getattr(uploaded, "name", "").lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded, dtype=str)
    return pd.read_csv(uploaded, dtype=str, encoding="utf-8-sig")


def normalise(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Map the file's own headings onto ours. Returns the renamed frame and any missing columns."""
    keyed = {re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_"): c for c in df.columns}
    rename = {}
    for target, options in ALIASES.items():
        for opt in options:
            if opt in keyed and keyed[opt] not in rename:
                rename[keyed[opt]] = target
                break
    out = df.rename(columns=rename)[list(rename.values())].copy()
    out = out.apply(lambda col: col.fillna("").astype(str).str.strip())
    return out, [c for c in REQUIRED if c not in out.columns]


def _locations():
    rows = fetchall("""SELECT sa.id area_id, sa.facility_id, sa.name area, f.name facility
                       FROM service_areas sa JOIN facilities f ON f.id=sa.facility_id
                       WHERE sa.active=1 AND f.active=1""")
    return rows


def preview(df: pd.DataFrame, data_source: str, facility_id: int | None = None) -> pd.DataFrame:
    """One row per file row with the action the import would take, or the problem that blocks it.

    With facility_id, the file is the resident list for that site only: dining areas are matched within the
    site, rows naming another facility are flagged, and only that site's missing residents are removed.
    """
    data, missing = normalise(df)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing).replace("_", " "))
    locations = _locations()
    site_name = None
    if facility_id is not None:
        locations = [l for l in locations if l["facility_id"] == facility_id]
        site_name = next((l["facility"] for l in _locations() if l["facility_id"] == facility_id), None)
    existing = {r["resident_code"]: r for r in fetchall(
        """SELECT r.*, sa.name area FROM intake_residents r JOIN service_areas sa ON sa.id=r.service_area_id""")}
    counts = data["resident_id"].str.upper().value_counts()

    out = []
    for i, row in data.iterrows():
        rid = row["resident_id"].upper()
        problems = []
        if not ID_PATTERN.fullmatch(rid):
            problems.append("Resident ID must be 3-25 letters, numbers or hyphens")
        elif counts.get(rid, 0) > 1:
            problems.append("Resident ID appears more than once")
        elif rid.startswith("DEMO-"):
            problems.append("IDs starting DEMO- are reserved for generated residents")
        if not row["name"]:
            problems.append("Name missing")
        if not row["room"]:
            problems.append("Room missing")

        area_name, fac_name = row["dining_area"].lower(), row.get("facility", "").lower()
        if site_name and fac_name and fac_name != site_name.lower():
            problems.append(f"Facility '{row['facility']}' is not the selected site ({site_name})")
            fac_name = site_name.lower()
        matches = [l for l in locations if l["area"].lower() == area_name
                   and (not fac_name or l["facility"].lower() == fac_name)]
        loc = matches[0] if len(matches) == 1 else None
        if not row["dining_area"]:
            problems.append("Dining area missing")
        elif not matches:
            if site_name and not locations:
                problems.append(f"{site_name} has no dining areas yet - add them in Menu & Locations first")
            else:
                problems.append(f"Dining area '{row['dining_area']}' not found"
                                + (f" at {site_name}" if site_name else ""))
        elif len(matches) > 1:
            problems.append(f"'{row['dining_area']}' exists in more than one facility - add a Facility column")

        menu_raw = row.get("menu_type", "") or "Regular"
        menu = parse_texture(menu_raw)
        if menu is None:
            problems.append(f"Diet '{menu_raw}' not recognised - use Regular, Soft & Bite-Sized, "
                            "Minced & Moist or Pureed")

        status = (row.get("status", "") or "Active").lower()
        if status in ("active", "yes", "y", "1", "current"):
            active = 1
        elif status in ("discharged", "inactive", "no", "n", "0", "left", "deceased"):
            active = 0
        else:
            active = None
            problems.append(f"Status '{row.get('status')}' should be Active or Discharged")

        current = existing.get(rid)
        if current is not None and current["data_source"] != data_source:
            problems.append("This Resident ID is already used by the other data source")

        action, changes = "Error", ""
        if not problems:
            if current is None:
                action = "New" if active else "Skip (discharged, not on file)"
            else:
                diffs = []
                if current["display_name"] != row["name"]:
                    diffs.append("name")
                if (current["room"] or "") != row["room"]:
                    diffs.append(f"room {current['room']} → {row['room']}")
                if current["service_area_id"] != loc["area_id"]:
                    diffs.append(f"area {current['area']} → {loc['area']}")
                if current["menu_variant"] != menu:
                    diffs.append(f"diet {texture_label(current['menu_variant'])} → {texture_label(menu)}")
                if not active and current["active"]:
                    action = "Discharge"
                elif active and not current["active"]:
                    action, diffs = "Re-admit", diffs
                else:
                    action = "Update" if diffs else "No change"
                changes = ", ".join(diffs)
        out.append({
            "Row": i + 2, "Resident ID": rid, "Name": row["name"], "Room": row["room"],
            "Dining area": f"{loc['facility']} / {loc['area']}" if loc else row["dining_area"],
            "Diet": texture_label(menu) if menu else menu_raw, "_menu": menu, "Action": action, "Changes": changes, "Problem": "; ".join(problems),
            "_area_id": loc["area_id"] if loc else None, "_facility_id": loc["facility_id"] if loc else None,
            "_active": active,
        })
    # The file replaces the list: active residents missing from it are taken off the nurse screen.
    # Safety: a file where no row is usable (e.g. the wrong site's file) never removes anyone.
    if not any(r["Action"] != "Error" for r in out):
        plan = pd.DataFrame(out)
        if not plan.empty:
            plan["Row"] = plan["Row"].astype("Int64")
        return plan
    in_file = set(data["resident_id"].str.upper())
    for code, cur in existing.items():
        if (cur["data_source"] == data_source and cur["active"] and code not in in_file
                and (facility_id is None or cur["facility_id"] == facility_id)):
            out.append({
                "Row": None, "Resident ID": code, "Name": cur["display_name"] or "", "Room": cur["room"] or "",
                "Dining area": cur["area"], "Diet": texture_label(cur["menu_variant"]), "_menu": cur["menu_variant"],
                "Action": "Remove (not in file)", "Changes": "", "Problem": "",
                "_area_id": cur["service_area_id"], "_facility_id": cur["facility_id"], "_active": 0,
            })
    plan = pd.DataFrame(out)
    if not plan.empty:
        plan["Row"] = plan["Row"].astype("Int64")  # removed residents have no file row: shown blank
    return plan


def apply(plan: pd.DataFrame, data_source: str, user_id: int | None) -> dict:
    """Save the previewed rows that have no problems."""
    counts = {"New": 0, "Update": 0, "Discharge": 0, "Re-admit": 0, "Remove (not in file)": 0}
    now = datetime.now().isoformat(timespec="seconds")
    with connection() as c:
        for _, r in plan.iterrows():
            action = r["Action"]
            if action not in counts:
                continue
            values = (r["Name"], r["Room"], int(r["_facility_id"]), int(r["_area_id"]), r["_menu"])
            if action == "New":
                c.execute(
                    """INSERT INTO intake_residents(display_name,room,facility_id,service_area_id,menu_variant,
                           resident_code,data_source,active,created_at,created_by) VALUES(?,?,?,?,?,?,?,1,?,?)""",
                    values + (r["Resident ID"], data_source, now, user_id),
                )
            elif action == "Remove (not in file)":
                c.execute("UPDATE intake_residents SET active=0 WHERE resident_code=? AND data_source=?",
                          (r["Resident ID"], data_source))
            else:
                c.execute(
                    """UPDATE intake_residents SET display_name=?,room=?,facility_id=?,service_area_id=?,
                           menu_variant=?,active=? WHERE resident_code=? AND data_source=?""",
                    values + (int(r["_active"]), r["Resident ID"], data_source),
                )
            counts[action] += 1
        c.execute("INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
                  (now, user_id, "IMPORT_RESIDENTS", f"{data_source}: {counts}"))
    return counts


def template_csv() -> bytes:
    return (",".join(TEMPLATE_COLUMNS) + "\n").encode("utf-8")
