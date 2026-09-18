from __future__ import annotations

from datetime import datetime
import pandas as pd

from .db import connection
from .costing import food_cost_per_kg

REQUIRED_WASTE_COLUMNS = [
    "service_date",
    "facility",
    "service_area",
    "meal",
    "food_item",
    "waste_type",
    "waste_kg",
]
OPTIONAL_WASTE_COLUMNS = [
    "prepared_kg",
    "served_kg",
    "resident_count",
    "waste_reason",
    "notes",
]


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [
        str(c).strip().lower().replace(" ", "_").replace("/", "_") for c in out.columns
    ]
    aliases = {
        "date": "service_date",
        "site": "facility",
        "dining_area": "service_area",
        "service_area_name": "service_area",
        "meal_service": "meal",
        "item": "food_item",
        "food": "food_item",
        "waste": "waste_kg",
        "waste_weight": "waste_kg",
        "weight_kg": "waste_kg",
        "prepared": "prepared_kg",
        "served": "served_kg",
        "residents": "resident_count",
        "reason": "waste_reason",
    }
    out = out.rename(columns={k: v for k, v in aliases.items() if k in out.columns and v not in out.columns})
    return out


def validate_waste_dataframe(df: pd.DataFrame):
    out = normalise_columns(df)
    missing = [c for c in REQUIRED_WASTE_COLUMNS if c not in out.columns]
    problems = []
    if missing:
        problems.append("Missing required columns: " + ", ".join(missing))
        return out, problems

    valid_types = {"Production Waste", "Plate Waste"}
    bad_types = out[~out["waste_type"].astype(str).str.strip().isin(valid_types)]
    if not bad_types.empty:
        problems.append(
            f"{len(bad_types)} row(s) have invalid waste_type. Use exactly 'Production Waste' or 'Plate Waste'."
        )

    dates = pd.to_datetime(out["service_date"], errors="coerce")
    if dates.isna().any():
        problems.append(f"{int(dates.isna().sum())} row(s) have invalid service_date values.")

    waste = pd.to_numeric(out["waste_kg"], errors="coerce")
    if waste.isna().any() or (waste < 0).any():
        problems.append("waste_kg must contain non-negative numeric values.")

    return out, problems


def _num(value):
    if pd.isna(value) or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _text(value):
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s or None


def import_waste_dataframe(df: pd.DataFrame, recorded_by: int | None = None):
    clean, problems = validate_waste_dataframe(df)
    if problems:
        return {"inserted": 0, "problems": problems}

    inserted = 0
    with connection() as c:
        c.execute("INSERT OR IGNORE INTO food_categories(name) VALUES('Imported Harbison Data')")
        import_cat = c.execute("SELECT id FROM food_categories WHERE name='Imported Harbison Data'").fetchone()[0]

        for _, row in clean.iterrows():
            facility = str(row["facility"]).strip()
            area = str(row["service_area"]).strip()
            meal = str(row["meal"]).strip()
            food = str(row["food_item"]).strip()
            waste_type = str(row["waste_type"]).strip()
            service_date = pd.to_datetime(row["service_date"]).date().isoformat()
            waste_kg = float(row["waste_kg"])
            prepared = _num(row.get("prepared_kg"))
            served = _num(row.get("served_kg"))
            residents = _num(row.get("resident_count"))
            reason = _text(row.get("waste_reason"))
            notes = _text(row.get("notes"))

            c.execute("INSERT OR IGNORE INTO facilities(name,active) VALUES(?,1)", (facility,))
            fid = c.execute("SELECT id FROM facilities WHERE name=?", (facility,)).fetchone()[0]
            c.execute("INSERT OR IGNORE INTO service_areas(facility_id,name,active) VALUES(?,?,1)", (fid, area))
            aid = c.execute("SELECT id FROM service_areas WHERE facility_id=? AND name=?", (fid, area)).fetchone()[0]
            c.execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,99)", (meal,))
            mid = c.execute("SELECT id FROM meals WHERE name=?", (meal,)).fetchone()[0]
            c.execute(
                """INSERT INTO food_items(name,category_id,manual_cost_per_kg,active)
                   VALUES(?,?,NULL,1)
                   ON CONFLICT(name) DO UPDATE SET active=1""",
                (food, import_cat),
            )
            food_id = c.execute("SELECT id FROM food_items WHERE name=?", (food,)).fetchone()[0]

            denominator = prepared if waste_type == "Production Waste" else served
            waste_pct = waste_kg / denominator * 100 if denominator and denominator > 0 else None
            cost, _ = food_cost_per_kg(food_id, service_date)
            waste_cost = waste_kg * cost if cost is not None else None

            c.execute(
                """INSERT INTO transactions(
                   created_at,service_date,facility_id,service_area_id,meal_id,food_item_id,waste_type,
                   prepared_kg,served_kg,waste_kg,waste_percentage,cost_per_kg_snapshot,waste_cost,
                   waste_reason,resident_count,notes,recorded_by,is_demo)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    datetime.now().isoformat(timespec="seconds"), service_date, fid, aid, mid, food_id,
                    waste_type, prepared, served, waste_kg, waste_pct, cost, waste_cost, reason,
                    int(residents) if residents is not None else None, notes, recorded_by,
                ),
            )
            inserted += 1

    return {"inserted": inserted, "problems": []}
