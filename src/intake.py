"""Resident Meal & Consumption Records: resident meal orders, consumption recording and corrections.

Terminology used throughout the module and UI:
- Served weight: grams actually provided to the resident for each food item.
- Observed intake: staff visual estimate of the portion eaten (0/25/50/75/100%).
- Estimated consumed weight can be calculated from served grams x observed intake, but this is
  resident-consumption detail only and is never treated as measured kitchen waste.
- Measured plate waste: weighed kg entered separately on the Food Waste Management Record Waste page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from .db import connection, fetchall, fetchone, setting
from .intake_db import COMPONENT_GROUPS, DATA_SOURCES, INTAKE_PERCENTAGES, MEAL_STATUSES
from .menu import menu_items, menu_week
from .textures import texture_label

DATA_SOURCE_LABELS = {"fictional_demo": "Synthetic data", "real": "Real"}

UNEATEN_REASONS = [
    "Poor appetite",
    "Disliked taste / food choice",
    "Texture or consistency",
    "Portion too large",
    "Temperature (too hot / too cold)",
    "Unwell or fatigued",
    "Needed assistance not available",
    "Asleep / drowsy",
    "Chewing or swallowing difficulty",
    "Ate other food (e.g. family, snacks)",
    "Other",
]

MISSED_REASONS = [
    "Out of facility (appointment / family)",
    "In hospital",
    "Asleep - not woken per care plan",
    "Fasting (medical instruction)",
    "Other",
]

_CARB_WORDS = ("potato", "mash", "rice", "pasta", "noodle", "bread", "toast", "roll", "couscous",
               "porridge", "cereal", "muesli", "oat", "pancake", "crumpet", "muffin", "scone", "wedges", "chips")
_PROTEIN_WORDS = ("egg", "chicken", "beef", "lamb", "pork", "fish", "salmon", "tuna", "turkey", "ham",
                  "bacon", "sausage", "mince", "tofu", "lentil", "chickpea", "bean", "yoghurt", "cheese")
_DRINK_WORDS = ("juice", "tea", "coffee", "milk drink", "smoothie", "water", "cordial", "milkshake", "drink")


def _has_word(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", text) for w in words)


def component_group_for(menu_component: str | None, category: str | None, label: str | None) -> str:
    """Suggest a component group for a menu item. Staff can change the suggestion when recording."""
    comp = (menu_component or "").lower()
    cat = (category or "").lower()
    text = (label or "").lower()
    if "soup" in text or "soup" in cat or "soup" in comp:
        return "soup"
    if "dessert" in comp or "dessert" in cat:
        return "dessert"
    if _has_word(text, _DRINK_WORDS) or "drink" in cat or "beverage" in cat:
        return "drinks"
    if "vegetarian" in comp or "vegetarian" in cat:
        return "protein"  # a vegetarian main dish, not a vegetable side
    if "carbohydrate" in comp or "carbohydrate" in cat:
        return "carbohydrate"
    if "tea" in comp or "snack" in cat or "salad" in comp:
        return "other"
    if "breakfast" in comp or "breakfast" in cat:
        return "protein" if _has_word(text, ("egg", "bacon", "sausage", "ham")) else "carbohydrate"
    if "side" in comp or "veg" in cat or "veg" in comp:
        return "carbohydrate" if _has_word(text, _CARB_WORDS) else "vegetables"
    if "main" in comp or "main" in cat:
        return "protein"
    if _has_word(text, _CARB_WORDS):
        return "carbohydrate"
    if _has_word(text, _PROTEIN_WORDS):
        return "protein"
    return "other"


def real_records_enabled() -> bool:
    return setting("intake_real_records_enabled", "0") == "1"


def allowed_sources() -> list[str]:
    return list(DATA_SOURCES) if real_records_enabled() else ["fictional_demo"]


# ---------------------------------------------------------------- residents and menu

def residents(data_source: str, facility_id: int | None = None, service_area_id: int | None = None,
              active_only: bool = True):
    sql = """SELECT r.*, f.name facility, sa.name service_area
             FROM intake_residents r
             JOIN facilities f ON f.id=r.facility_id
             JOIN service_areas sa ON sa.id=r.service_area_id
             WHERE r.data_source=?"""
    params: list = [data_source]
    if active_only:
        sql += " AND r.active=1"
    if facility_id:
        sql += " AND r.facility_id=?"
        params.append(facility_id)
    if service_area_id:
        sql += " AND r.service_area_id=?"
        params.append(service_area_id)
    sql += " ORDER BY CAST(r.room AS INTEGER), r.room, r.resident_code"
    return fetchall(sql, tuple(params))


def create_resident(code: str, facility_id: int, service_area_id: int, menu_variant: str,
                    data_source: str, user_id: int | None) -> int:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{2,24}", code):
        raise ValueError("Resident code must be 3-25 letters, digits or hyphens (no names).")
    if data_source not in allowed_sources():
        raise PermissionError("Real resident records are not enabled for this installation.")
    with connection() as c:
        cur = c.execute(
            """INSERT INTO intake_residents(resident_code,facility_id,service_area_id,menu_variant,
                   data_source,active,created_at,created_by) VALUES(?,?,?,?,?,1,?,?)""",
            (code, facility_id, service_area_id, menu_variant, data_source,
             datetime.now().isoformat(timespec="seconds"), user_id),
        )
        return int(cur.lastrowid)


def update_resident_location(resident_id: int, room: str, service_area_id: int, user_id: int | None) -> str | None:
    """Correct a resident's room / dining area. Returns a warning if another active resident already has that room."""
    room = (room or "").strip()
    if not room or len(room) > 10:
        raise ValueError("Room must be 1-10 characters.")
    with connection() as c:
        old = c.execute(
            """SELECT r.room, sa.name area FROM intake_residents r JOIN service_areas sa ON sa.id=r.service_area_id
               WHERE r.id=?""", (resident_id,)).fetchone()
        area = c.execute("SELECT facility_id, name FROM service_areas WHERE id=? AND active=1",
                         (service_area_id,)).fetchone()
        if old is None or area is None:
            raise ValueError("Resident or dining area not found.")
        clash = c.execute(
            """SELECT display_name, resident_code FROM intake_residents
               WHERE service_area_id=? AND room=? AND id<>? AND active=1""",
            (service_area_id, room, resident_id)).fetchone()
        c.execute("UPDATE intake_residents SET room=?, service_area_id=?, facility_id=? WHERE id=?",
                  (room, service_area_id, area["facility_id"], resident_id))
        _audit(c, user_id, "RESIDENT_MOVED",
               f"resident {resident_id}: room {old['room']} -> {room}, area {old['area']} -> {area['name']}")
    if clash:
        return f"Room {room} in {area['name']} is also assigned to {clash['display_name'] or clash['resident_code']}."
    return None


def meal_id_for(meal_service: str) -> int:
    row = fetchone("SELECT id FROM meals WHERE name=?", (meal_service,))
    if row:
        return row["id"]
    with connection() as c:
        c.execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,99)", (meal_service,))
        return c.execute("SELECT id FROM meals WHERE name=?", (meal_service,)).fetchone()[0]


def menu_components_for_meal(d: date, meal_service: str, variant: str) -> list[dict]:
    """Menu items for a resident's texture. If the menu has no version for that texture, the Regular dish
    is used and labelled with the texture (e.g. 'Roast Chicken (Minced & Moist)') for the kitchen."""
    items = menu_items(d, meal_service, variant)
    suffix = ""
    if not items:
        items = menu_items(d, meal_service, "Regular")
        suffix = "" if variant in (None, "", "Regular") else f" ({texture_label(variant)})"
    return [
        {
            "food_item_id": it["id"],
            "item_label": it["name"] + suffix,
            "component_group": component_group_for(it.get("component"), it.get("category"), it["name"]),
            "menu_component": it.get("component"),
        }
        for it in items
    ]


# ---------------------------------------------------------------- meal orders

PLATE_MEALS = ["Breakfast", "Morning Tea", "Lunch", "Afternoon Tea", "Dinner"]
MEAL_LABELS = {"Breakfast": "Breakfast", "Morning Tea": "Morning tea", "Lunch": "Lunch",
               "Afternoon Tea": "Afternoon tea", "Dinner": "Dinner"}


def add_order(resident_id: int, service_date: date, meal_service: str, item_label: str,
              component_group: str, food_item_id: int | None, user_id: int | None) -> None:
    label = (item_label or "").strip()
    if not label:
        raise ValueError("Item name is required.")
    if component_group not in COMPONENT_GROUPS:
        raise ValueError("Unknown item type.")
    with connection() as c:
        src = c.execute("SELECT data_source FROM intake_residents WHERE id=?", (resident_id,)).fetchone()
        if src is None:
            raise ValueError("Resident not found.")
        c.execute(
            """INSERT OR IGNORE INTO intake_meal_orders(resident_id,service_date,meal_id,item_label,
                   component_group,food_item_id,data_source,ordered_by,ordered_at)
               VALUES(?,?,(SELECT id FROM meals WHERE name=?),?,?,?,?,?,?)""",
            (resident_id, service_date.isoformat(), meal_service, label[:80], component_group, food_item_id,
             src[0], user_id, datetime.now().isoformat(timespec="seconds")),
        )


def standard_plate(items: list[dict], meal_service: str, choose=None) -> list[dict]:
    """One sensible plate from the day's menu rather than every option on it.

    Breakfast: continental (or the hot ASF option when chosen). Lunch / dinner: one main (Main Choice 1 by
    default; Main Choice 2 or vegetarian when chosen), plus soup, vegetables, carbohydrate and dessert.
    `choose(options)` picks among alternatives; by default the first one is used.
    """
    choose = choose or (lambda options: options[0])
    by_comp: dict[str, list[dict]] = {}
    for it in items:
        by_comp.setdefault((it.get("menu_component") or "").lower(), []).append(it)
    if meal_service == "Breakfast":
        options = by_comp.get("continental", []) + by_comp.get("hot breakfast", [])
        return [choose(options)] if options else items[:1]
    if meal_service not in ("Lunch", "Dinner"):
        return []
    mains = (by_comp.get("main choice 1", []) + by_comp.get("main", []) + by_comp.get("main choice 2", [])
             + by_comp.get("vegetarian", []))
    plate = [choose(mains)] if mains else []
    for comp in ("soup", "vegetables", "carbohydrate", "dessert"):
        plate += by_comp.get(comp, [])[:1]
    known = {"continental", "hot breakfast", "main choice 1", "main", "main choice 2", "vegetarian", "soup",
             "vegetables", "carbohydrate", "dessert", "salad / sandwich"}
    plate += [it for comp, its in by_comp.items() if comp not in known for it in its]  # older menu formats
    return plate


def ensure_standard_orders(people: list[dict], service_date: date, meal_service: str) -> int:
    """Give residents with no order for this meal the standard menu order, so nurses can record straight away.

    Main meals: one plate from that day's four-week menu for the resident's diet (see standard_plate).
    Morning / afternoon tea: tea.
    """
    have = {r["resident_id"] for r in fetchall(
        """SELECT DISTINCT o.resident_id FROM intake_meal_orders o JOIN meals m ON m.id=o.meal_id
           WHERE o.service_date=? AND m.name=?""", (service_date.isoformat(), meal_service))}
    missing = [p for p in people if p["id"] not in have]
    if not missing:
        return 0
    menus: dict[str, list[dict]] = {}
    rows = []
    for p in missing:
        if meal_service in ("Morning Tea", "Afternoon Tea"):
            items = [{"item_label": "Tea", "component_group": "drinks", "food_item_id": None}]
        else:
            variant = p["menu_variant"]
            if variant not in menus:
                menus[variant] = standard_plate(menu_components_for_meal(service_date, meal_service, variant),
                                                meal_service)
            items = list(menus[variant])
        rows += [(p["id"], it["item_label"], it["component_group"], it["food_item_id"], p["data_source"])
                 for it in items]
    now = datetime.now().isoformat(timespec="seconds")
    with connection() as c:
        meal_id = c.execute("SELECT id FROM meals WHERE name=?", (meal_service,)).fetchone()[0]
        c.executemany(
            """INSERT OR IGNORE INTO intake_meal_orders(resident_id,service_date,meal_id,item_label,component_group,
                   food_item_id,data_source,ordered_by,ordered_at) VALUES(?,?,?,?,?,?,?,NULL,?)""",
            [(rid, service_date.isoformat(), meal_id, label, group, fid, src, now)
             for rid, label, group, fid, src in rows],
        )
    return len(missing)


def orders_for(data_source: str, service_date: date, meal_service: str) -> dict[int, list[dict]]:
    """Ordered items per resident for one meal, keyed by resident id."""
    rows = fetchall(
        """SELECT o.resident_id,o.item_label,o.component_group,o.food_item_id
           FROM intake_meal_orders o JOIN meals m ON m.id=o.meal_id
           WHERE o.data_source=? AND o.service_date=? AND m.name=?
           ORDER BY o.resident_id, CASE o.component_group WHEN 'soup' THEN 0 WHEN 'protein' THEN 1
                    WHEN 'carbohydrate' THEN 2 WHEN 'vegetables' THEN 3 WHEN 'dessert' THEN 4
                    WHEN 'drinks' THEN 5 ELSE 6 END, o.id""",
        (data_source, service_date.isoformat(), meal_service),
    )
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["resident_id"], []).append(r)
    return out


def meal_results(data_source: str, service_date: date, meal_service: str) -> dict[int, dict]:
    """Current recorded result per resident for one meal: status and mean observed intake."""
    rows = fetchall(
        """SELECT o.resident_id,o.meal_status,AVG(c.intake_pct) avg_pct,SUM(c.served_weight_g) served_g
           FROM intake_meal_observations o JOIN meals m ON m.id=o.meal_id
           LEFT JOIN intake_component_observations c ON c.observation_id=o.id
           WHERE o.data_source=? AND o.service_date=? AND m.name=? AND o.is_current=1
           GROUP BY o.id""",
        (data_source, service_date.isoformat(), meal_service),
    )
    return {r["resident_id"]: r for r in rows}


def day_overview(data_source: str, service_date: date, service_area_id: int | None = None,
                 facility_id: int | None = None) -> pd.DataFrame:
    """One row per resident, one column per meal: what was ordered and how much was eaten."""
    people = residents(data_source, facility_id=facility_id, service_area_id=service_area_id)
    table = {p["id"]: {"Room": p["room"] or "", "Name": p.get("display_name") or p["resident_code"],
                       "Diet": texture_label(p["menu_variant"])} for p in people}
    for meal in PLATE_MEALS:
        orders = orders_for(data_source, service_date, meal)
        results = meal_results(data_source, service_date, meal)
        for rid, row in table.items():
            items = ", ".join(o["item_label"] for o in orders.get(rid, []))
            res = results.get(rid)
            if res is None:
                cell = items or "-"
            elif res["meal_status"] == "refused":
                cell = "Refused"
            elif res["meal_status"] == "missed":
                cell = "Missed"
            elif res["avg_pct"] is None:
                cell = "Not seen"
            else:
                served = f" · {res['served_g']:.0f} g served" if res.get('served_g') else ""
                cell = f"✓ {res['avg_pct']:.0f}% eaten{served}"
            row[MEAL_LABELS[meal]] = cell
    return pd.DataFrame(list(table.values()))


# ---------------------------------------------------------------- recording

@dataclass
class ComponentEntry:
    component_group: str
    item_label: str
    observed_status: str  # observed | not_observed | unknown
    intake_pct: int | None = None
    food_item_id: int | None = None
    reason_uneaten: str | None = None
    reason_other: str | None = None
    served_weight_g: float | None = None


@dataclass
class MealEntry:
    resident_id: int
    service_date: date
    meal_service: str
    meal_status: str
    components: list[ComponentEntry] = field(default_factory=list)
    missed_reason: str | None = None
    replacement_description: str | None = None
    staff_observation: str | None = None


def validate_entry(entry: MealEntry) -> list[str]:
    errors = []
    if entry.meal_status not in MEAL_STATUSES:
        errors.append("Unknown meal status.")
    if entry.service_date > date.today():
        errors.append("Observations cannot be recorded for a future date.")
    if entry.meal_status == "missed" and not entry.missed_reason:
        errors.append("Select a reason for the missed meal.")
    if entry.meal_status == "replacement" and not (entry.replacement_description or "").strip():
        errors.append("Describe the replacement meal provided.")
    if entry.meal_status in ("served", "replacement") and not entry.components:
        errors.append("Record at least one meal component.")
    if entry.staff_observation and len(entry.staff_observation) > 300:
        errors.append("Staff observation must be 300 characters or fewer.")
    for comp in entry.components:
        if comp.component_group not in COMPONENT_GROUPS:
            errors.append(f"Unknown component group for {comp.item_label}.")
        if comp.observed_status == "observed":
            if comp.intake_pct not in INTAKE_PERCENTAGES:
                errors.append(f"Select an intake percentage for {comp.item_label}.")
        elif comp.observed_status in ("not_observed", "unknown"):
            if comp.intake_pct is not None:
                errors.append(f"{comp.item_label}: 'not observed' / 'unknown' cannot have a percentage.")
        else:
            errors.append(f"Unknown observation status for {comp.item_label}.")
        if comp.reason_uneaten and comp.reason_uneaten not in UNEATEN_REASONS:
            errors.append(f"Unknown reason for {comp.item_label}.")
    return errors


def _insert_observation(c, entry: MealEntry, user_id: int | None, version: int = 1,
                        supersedes_id: int | None = None, correction_reason: str | None = None) -> int:
    res = c.execute(
        "SELECT facility_id,service_area_id,menu_variant,data_source FROM intake_residents WHERE id=?",
        (entry.resident_id,),
    ).fetchone()
    if res is None:
        raise ValueError("Resident not found.")
    if res["data_source"] == "real" and not real_records_enabled():
        raise PermissionError("Real resident records are not enabled for this installation.")
    meal_id = c.execute("SELECT id FROM meals WHERE name=?", (entry.meal_service,)).fetchone()
    if meal_id is None:
        raise ValueError(f"Unknown meal service {entry.meal_service}.")
    cur = c.execute(
        """INSERT INTO intake_meal_observations(
               resident_id,service_date,meal_id,facility_id,service_area_id,menu_variant,menu_week,
               meal_status,missed_reason,replacement_description,staff_observation,data_source,
               version,supersedes_id,is_current,correction_reason,recorded_by,recorded_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
        (
            entry.resident_id, entry.service_date.isoformat(), meal_id[0], res["facility_id"],
            res["service_area_id"], res["menu_variant"], menu_week(entry.service_date), entry.meal_status,
            entry.missed_reason if entry.meal_status == "missed" else None,
            ((entry.replacement_description or "").strip() or None) if entry.meal_status == "replacement" else None,
            (entry.staff_observation or "").strip() or None, res["data_source"],
            version, supersedes_id, correction_reason, user_id, datetime.now().isoformat(timespec="seconds"),
        ),
    )
    obs_id = int(cur.lastrowid)
    if entry.meal_status in ("served", "replacement"):
        for comp in entry.components:
            c.execute(
                """INSERT INTO intake_component_observations(
                       observation_id,component_group,food_item_id,item_label,observed_status,
                       intake_pct,served_weight_g,reason_uneaten,reason_other)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    obs_id, comp.component_group, comp.food_item_id, comp.item_label.strip(),
                    comp.observed_status, comp.intake_pct if comp.observed_status == "observed" else None,
                    comp.served_weight_g, comp.reason_uneaten, (comp.reason_other or "").strip() or None,
                ),
            )
    return obs_id


def save_observation(entry: MealEntry, user_id: int | None) -> int:
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    with connection() as c:
        existing = c.execute(
            """SELECT o.id FROM intake_meal_observations o JOIN meals m ON m.id=o.meal_id
               WHERE o.resident_id=? AND o.service_date=? AND m.name=? AND o.is_current=1""",
            (entry.resident_id, entry.service_date.isoformat(), entry.meal_service),
        ).fetchone()
        if existing:
            raise FileExistsError("This meal is already recorded. An authorised user can record a correction.")
        obs_id = _insert_observation(c, entry, user_id)
        _audit(c, user_id, "INTAKE_RECORD", f"observation {obs_id}")
    return obs_id


def correct_observation(original_id: int, entry: MealEntry, reason: str, user_id: int | None) -> int:
    """Supersede the current version with a corrected one; the original row is kept unchanged."""
    if not (reason or "").strip():
        raise ValueError("A correction reason is required.")
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    with connection() as c:
        old = c.execute("SELECT * FROM intake_meal_observations WHERE id=?", (original_id,)).fetchone()
        if old is None or not old["is_current"]:
            raise ValueError("Only the current version of a record can be corrected.")
        if old["resident_id"] != entry.resident_id or old["service_date"] != entry.service_date.isoformat():
            raise ValueError("A correction must keep the same resident and date.")
        c.execute("UPDATE intake_meal_observations SET is_current=0 WHERE id=?", (original_id,))
        new_id = _insert_observation(c, entry, user_id, version=old["version"] + 1,
                                     supersedes_id=original_id, correction_reason=reason.strip()[:300])
        _audit(c, user_id, "INTAKE_CORRECTION", f"observation {original_id} -> {new_id}: {reason.strip()[:120]}")
    return new_id


def _audit(c, user_id, action, details):
    c.execute(
        "INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), user_id, action, details),
    )


def current_observation(resident_id: int, service_date: date, meal_service: str):
    obs = fetchone(
        """SELECT o.*, m.name meal_service, COALESCE(u.display_name,'System') recorded_by_name
           FROM intake_meal_observations o JOIN meals m ON m.id=o.meal_id
           LEFT JOIN users u ON u.id=o.recorded_by
           WHERE o.resident_id=? AND o.service_date=? AND m.name=? AND o.is_current=1""",
        (resident_id, service_date.isoformat(), meal_service),
    )
    if obs:
        obs["components"] = fetchall(
            "SELECT * FROM intake_component_observations WHERE observation_id=? ORDER BY id", (obs["id"],)
        )
    return obs


def observation_history(observation_id: int) -> list[dict]:
    """All versions of a record, newest first, following the supersedes chain both ways."""
    with connection() as c:
        ids = {observation_id}
        frontier = [observation_id]
        while frontier:
            q = ",".join("?" * len(frontier))
            rows = c.execute(
                f"""SELECT id,supersedes_id FROM intake_meal_observations
                    WHERE id IN ({q}) OR supersedes_id IN ({q})""",
                tuple(frontier) * 2,
            ).fetchall()
            frontier = []
            for r in rows:
                for x in (r["id"], r["supersedes_id"]):
                    if x and x not in ids:
                        ids.add(x)
                        frontier.append(x)
        q = ",".join("?" * len(ids))
        versions = [dict(r) for r in c.execute(
            f"""SELECT o.*, COALESCE(u.display_name,'System') recorded_by_name
                FROM intake_meal_observations o LEFT JOIN users u ON u.id=o.recorded_by
                WHERE o.id IN ({q}) ORDER BY o.version DESC""",
            tuple(ids),
        ).fetchall()]
        for v in versions:
            v["components"] = [dict(r) for r in c.execute(
                "SELECT * FROM intake_component_observations WHERE observation_id=? ORDER BY id", (v["id"],)
            ).fetchall()]
    return versions


def recorded_resident_ids(service_date: date, meal_service: str, service_area_id: int, data_source: str) -> set[int]:
    rows = fetchall(
        """SELECT o.resident_id FROM intake_meal_observations o JOIN meals m ON m.id=o.meal_id
           WHERE o.service_date=? AND m.name=? AND o.service_area_id=? AND o.data_source=? AND o.is_current=1""",
        (service_date.isoformat(), meal_service, service_area_id, data_source),
    )
    return {r["resident_id"] for r in rows}


# ---------------------------------------------------------------- analysis frames

def meal_level_frame(data_source: str, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """One row per current meal observation with derived meal intake.

    meal_intake_pct:
      served / replacement -> mean of observed components (NaN if none observed)
      refused              -> 0 (the resident was offered the meal and ate none)
      missed               -> NaN (not offered; excluded from intake averages)
    """
    where = ["o.is_current=1", "o.data_source=?"]
    params: list = [data_source]
    if start:
        where.append("o.service_date>=?")
        params.append(start.isoformat())
    if end:
        where.append("o.service_date<=?")
        params.append(end.isoformat())
    sql = f"""
        SELECT o.id observation_id, o.resident_id, r.resident_code, o.service_date, m.name meal_service,
               m.sort_order meal_order, f.name facility, sa.name service_area, o.facility_id, o.service_area_id,
               o.menu_variant, o.menu_week, o.meal_status, o.missed_reason, o.version, o.data_source,
               SUM(CASE WHEN c.observed_status='observed' THEN 1 ELSE 0 END) observed_components,
               SUM(CASE WHEN c.observed_status<>'observed' THEN 1 ELSE 0 END) unobserved_components,
               AVG(c.intake_pct) avg_component_pct
        FROM intake_meal_observations o
        JOIN intake_residents r ON r.id=o.resident_id
        JOIN meals m ON m.id=o.meal_id
        JOIN facilities f ON f.id=o.facility_id
        JOIN service_areas sa ON sa.id=o.service_area_id
        LEFT JOIN intake_component_observations c ON c.observation_id=o.id
        WHERE {' AND '.join(where)}
        GROUP BY o.id
        ORDER BY o.service_date, m.sort_order, r.resident_code"""
    with connection() as c:
        df = pd.read_sql_query(sql, c, params=params)
    if df.empty:
        return df
    df["service_date"] = pd.to_datetime(df["service_date"])
    df["meal_intake_pct"] = df["avg_component_pct"]
    df.loc[df.meal_status == "refused", "meal_intake_pct"] = 0.0
    df.loc[df.meal_status == "missed", "meal_intake_pct"] = float("nan")
    df["documented"] = df["meal_intake_pct"].notna() | (df.meal_status == "missed")
    df["estimated_leftover_pct"] = 100 - df["meal_intake_pct"]
    return df
