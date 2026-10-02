from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import numpy as np

from .db import connection, fetchone


VARIANT_SHARES = {
    "Regular": 0.60,
    "Soft Bite Sized": 0.20,
    "Minced": 0.10,
    "Puree": 0.10,
}

CATEGORY_PORTION_KG = {
    "Main": 0.230,
    "Dessert": 0.090,
    "Tea / Snack": 0.080,
    "Vegetarian": 0.220,
    "Breakfast": 0.180,
    "Carbohydrate": 0.120,
    "Vegetable": 0.090,
    "Soup": 0.240,
    "Salad / Sandwich": 0.150,
}

CATEGORY_PLATE_WASTE = {
    "Main": 0.16,
    "Dessert": 0.14,
    "Tea / Snack": 0.10,
    "Vegetarian": 0.19,
    "Breakfast": 0.12,
    "Carbohydrate": 0.15,
    "Vegetable": 0.20,
    "Soup": 0.13,
    "Salad / Sandwich": 0.18,
}


@dataclass
class GenerationConfig:
    start_date: date
    end_date: date
    seed: int = 42
    resident_min: int = 88
    resident_max: int = 108
    fallback_facilities: int = 2
    fallback_areas_per_facility: int = 2
    replace_existing: bool = True



def _stable01(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)



def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))



def _iter_dates(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)



def _participation(component: str, category: str, preference: float) -> float:
    c = (component or "").lower()
    base = 0.85
    if "lunch main choice 1" in c:
        base = 0.48
    elif "lunch main choice 2" in c:
        base = 0.28
    elif "vegetarian option" in c or "vegetarian evening" in c:
        base = 0.12
    elif "salads and sandwiches" in c:
        base = 0.12
    elif "breakfast - asf" in c:
        base = 0.34
    elif c in {"minced", "puree"}:
        base = 0.88
    elif "carbohydrate" in c or "feature veg" in c:
        base = 0.90
    elif "dessert" in c:
        base = 0.77
    elif "soup" in c:
        base = 0.70
    elif "morning tea" in c or "afternoon tea" in c:
        base = 0.82
    elif "evening meal" in c:
        base = 0.86
    elif "breakfast" in c:
        base = 0.92

    # Stable item preference creates learnable food-specific demand differences.
    return _clip(base + (preference - 0.5) * 0.10, 0.05, 0.98)



def _portion_kg(category: str, component: str, recipe_serving_kg: float | None, label: str) -> float:
    if recipe_serving_kg and recipe_serving_kg > 0:
        return float(recipe_serving_kg)
    portion = CATEGORY_PORTION_KG.get(category or "", 0.180)
    c = (component or "").lower()
    if "feature veg" in c:
        portion = 0.085
    elif "carbohydrate" in c:
        portion = 0.115
    elif "dessert" in c:
        portion = 0.090
    elif "soup" in c:
        portion = 0.240
    elif "tea" in c:
        portion = 0.075
    elif "breakfast" in c and "asf" not in c:
        portion = 0.170
    elif "minced" in c or "puree" in c:
        portion = 0.260

    # Small stable food-specific variation keeps menu items distinct.
    return portion * (0.92 + 0.16 * _stable01(f"portion|{label}"))



def _plate_waste_ratio(
    category: str,
    variant: str,
    meal: str,
    preference: float,
    service_shock: float,
    rng: np.random.Generator,
) -> float:
    """Simulate plate-waste percentage with stable food effects plus real-day variation."""
    base = CATEGORY_PLATE_WASTE.get(category or "", 0.16)
    variant_adj = {
        "Regular": 0.00,
        "Soft Bite Sized": 0.018,
        "Minced": 0.035,
        "Puree": 0.050,
    }.get(variant, 0.0)
    meal_adj = {
        "Breakfast": -0.015,
        "Morning Tea": -0.020,
        "Lunch": 0.010,
        "Afternoon Tea": -0.015,
        "Dinner": 0.015,
    }.get(meal, 0.0)
    pref_adj = (0.50 - preference) * 0.17
    # A difficult service can lift leftovers across many foods at once.
    service_adj = -0.20 * service_shock
    noise = float(rng.normal(0.0, 0.024))
    return _clip(base + variant_adj + meal_adj + pref_adj + service_adj + noise, 0.025, 0.45)


def _prep_buffer(component: str, variant: str, participation: float) -> float:
    """Typical kitchen over-preparation allowance before random planning error."""
    c = (component or "").lower()
    base = 0.055
    if "main choice" in c:
        base = 0.085
    elif "vegetarian" in c:
        base = 0.095
    elif "salads and sandwiches" in c:
        base = 0.085
    elif "tea" in c:
        base = 0.060
    elif "dessert" in c:
        base = 0.055
    elif "soup" in c:
        base = 0.050
    elif "feature veg" in c or "carbohydrate" in c:
        base = 0.045
    if variant in {"Minced", "Puree"}:
        base += 0.012
    base += max(0.0, 0.75 - participation) * 0.045
    return _clip(base, 0.025, 0.16)


def _generic_service_label(label: str) -> bool:
    """Menu rows that are service headings rather than useful item-level ranking targets."""
    cleaned = " ".join((label or "").strip().lower().split())
    return cleaned in {
        "harbison morning tea",
        "harbison afternoon tea",
        "morning tea",
        "afternoon tea",
    }


def _ensure_locations(c, fallback_facilities: int, fallback_areas: int):
    rows = c.execute(
        """SELECT f.id facility_id,f.name facility,sa.id service_area_id,sa.name service_area
           FROM facilities f JOIN service_areas sa ON sa.facility_id=f.id
           WHERE f.active=1 AND sa.active=1 ORDER BY f.id,sa.id"""
    ).fetchall()
    if rows:
        return [dict(r) for r in rows], False

    created = []
    for fi in range(1, max(1, fallback_facilities) + 1):
        facility = f"Synthetic Harbison Site {fi}"
        c.execute("INSERT OR IGNORE INTO facilities(name,active) VALUES(?,1)", (facility,))
        facility_id = c.execute("SELECT id FROM facilities WHERE name=?", (facility,)).fetchone()[0]
        for ai in range(1, max(1, fallback_areas) + 1):
            area = f"Synthetic Dining Area {ai}"
            c.execute(
                "INSERT OR IGNORE INTO service_areas(facility_id,name,active) VALUES(?,?,1)",
                (facility_id, area),
            )
            area_id = c.execute(
                "SELECT id FROM service_areas WHERE facility_id=? AND name=?", (facility_id, area)
            ).fetchone()[0]
            created.append({
                "facility_id": facility_id,
                "facility": facility,
                "service_area_id": area_id,
                "service_area": area,
            })
    return created, True



def _variant_counts(total: int, rng: np.random.Generator) -> dict[str, int]:
    names = list(VARIANT_SHARES)
    centre = np.array([VARIANT_SHARES[n] for n in names], dtype=float)
    # Dirichlet provides day-to-day variation while remaining near the sponsor-inspired mix.
    shares = rng.dirichlet(centre * 120.0)
    raw = shares * total
    counts = np.floor(raw).astype(int)
    remainder = total - int(counts.sum())
    if remainder > 0:
        for idx in np.argsort(raw - counts)[::-1][:remainder]:
            counts[idx] += 1
    return {n: max(1, int(v)) for n, v in zip(names, counts)}



def estimate_transaction_count(start_date: date, end_date: date, locations: int = 4) -> int:
    if end_date < start_date:
        return 0
    days = (end_date - start_date).days + 1
    avg_menu_rows_per_day = fetchone("SELECT COUNT(*) n FROM harbison_menu_schedule")
    total_menu = int((avg_menu_rows_per_day or {}).get("n", 0))
    if total_menu <= 0:
        return 0
    daily = total_menu / 28.0
    return int(round(days * daily * max(1, locations) * 2))



def generate_synthetic_ml_data(config: GenerationConfig) -> dict:
    """Generate reproducible, menu-aligned synthetic production and plate-waste records.

    The generator uses only the imported Harbison four-week menu structure and confirmed
    recipe serving sizes where available. Supplier comparison rows are *not* treated as
    historical ordering records. Cost snapshots are therefore left unknown unless the app
    already has a confirmed cost for a food item.
    """
    if config.end_date < config.start_date:
        raise ValueError("End date must be on or after start date.")
    if config.resident_min < 1 or config.resident_max < config.resident_min:
        raise ValueError("Resident range is invalid.")

    rng = np.random.default_rng(int(config.seed))
    now = datetime.now().isoformat(timespec="seconds")

    with connection() as c:
        menu_count = c.execute("SELECT COUNT(*) FROM harbison_menu_schedule").fetchone()[0]
        if not menu_count:
            raise RuntimeError("No Harbison menu is loaded. Reconcile the sponsor menu before generating synthetic data.")

        # Schema upgrades are normally handled by init_db/migration, but keep this function safe.
        tx_cols = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
        if "synthetic_run_id" not in tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN synthetic_run_id INTEGER")
        c.execute(
            """CREATE TABLE IF NOT EXISTS synthetic_generation_runs(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   created_at TEXT NOT NULL,
                   seed INTEGER NOT NULL,
                   start_date TEXT NOT NULL,
                   end_date TEXT NOT NULL,
                   resident_min INTEGER NOT NULL,
                   resident_max INTEGER NOT NULL,
                   location_count INTEGER NOT NULL,
                   menu_rows_used INTEGER NOT NULL DEFAULT 0,
                   transactions_created INTEGER NOT NULL DEFAULT 0,
                   notes TEXT
               )"""
        )

        if config.replace_existing:
            c.execute("DELETE FROM transactions WHERE synthetic_run_id IS NOT NULL")
            c.execute("DELETE FROM synthetic_generation_runs")

        locations, created_fallback = _ensure_locations(
            c, config.fallback_facilities, config.fallback_areas_per_facility
        )

        c.execute(
            """INSERT INTO synthetic_generation_runs(
                   created_at,seed,start_date,end_date,resident_min,resident_max,location_count,notes)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                now,
                int(config.seed),
                config.start_date.isoformat(),
                config.end_date.isoformat(),
                int(config.resident_min),
                int(config.resident_max),
                len(locations),
                "Menu-aligned synthetic ML data. All resulting transactions are marked synthetic.",
            ),
        )
        run_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]

        ms = c.execute("SELECT cycle_start_date,cycle_weeks FROM menu_settings WHERE id=1").fetchone()
        cycle_start = date.fromisoformat(ms[0])
        cycle_weeks = int(ms[1])

        schedule_rows = [dict(r) for r in c.execute(
            """SELECT h.*,sr.serving_size_g
               FROM harbison_menu_schedule h
               LEFT JOIN sponsor_recipes sr ON sr.food_item_id=h.linked_recipe_food_item_id
               ORDER BY week_number,day_of_week,menu_variant,meal_service,component,menu_label"""
        ).fetchall()]
        by_day: dict[tuple[int, int], list[dict]] = {}
        for row in schedule_rows:
            by_day.setdefault((int(row["week_number"]), int(row["day_of_week"])), []).append(row)

        meal_ids = {}
        for meal in {r["meal_service"] for r in schedule_rows}:
            c.execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,99)", (meal,))
            meal_ids[meal] = c.execute("SELECT id FROM meals WHERE name=?", (meal,)).fetchone()[0]

        # Stable location effects make the generated dataset learnable without being trivial.
        loc_effect = {
            (loc["facility_id"], loc["service_area_id"]): 0.94 + 0.12 * _stable01(
                f"loc|{config.seed}|{loc['facility']}|{loc['service_area']}"
            )
            for loc in locations
        }

        insert_sql = """INSERT INTO transactions(
            created_at,service_date,facility_id,service_area_id,meal_id,food_item_id,
            waste_type,prepared_kg,served_kg,waste_kg,waste_percentage,
            cost_per_kg_snapshot,waste_cost,waste_reason,resident_count,notes,recorded_by,is_demo,
            menu_variant,menu_component,synthetic_run_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)"""

        rows_to_insert = []
        menu_rows_used = 0

        # Occupancy evolves through time instead of resetting around one fixed number every day.
        # This creates slow operational drift plus occasional short disruptions.
        midpoint = (config.resident_min + config.resident_max) / 2.0
        occupancy_state = {}
        occupancy_phase = {}
        for loc in locations:
            key = (loc["facility_id"], loc["service_area_id"])
            occupancy_state[key] = float(rng.integers(config.resident_min, config.resident_max + 1))
            occupancy_phase[key] = 2.0 * math.pi * _stable01(
                f"occ-phase|{config.seed}|{loc['facility']}|{loc['service_area']}"
            )

        current_week_key = None
        weekly_site_shock = {}
        weekly_meal_shock = {}

        for service_date in _iter_dates(config.start_date, config.end_date):
            menu_week = ((service_date - cycle_start).days // 7) % cycle_weeks + 1
            day_rows = by_day.get((menu_week, service_date.weekday()), [])
            if not day_rows:
                continue

            elapsed_days = (service_date - config.start_date).days
            year_day = service_date.timetuple().tm_yday
            # Low-amplitude seasonal signal that the calendar features can partly learn.
            seasonal = 1.0 + 0.030 * math.sin(2.0 * math.pi * year_day / 365.25)
            weekend = 0.975 if service_date.weekday() >= 5 else 1.0

            week_key = service_date - timedelta(days=service_date.weekday())
            if week_key != current_week_key:
                current_week_key = week_key
                weekly_site_shock = {
                    (loc["facility_id"], loc["service_area_id"]): float(rng.normal(0.0, 0.045))
                    for loc in locations
                }
                weekly_meal_shock = {
                    meal: float(rng.normal(0.0, 0.030))
                    for meal in meal_ids
                }

            for loc in locations:
                key = (loc["facility_id"], loc["service_area_id"])
                # Slow occupancy wave + autocorrelation.  A rare event can change attendance more sharply.
                slow_target = midpoint + 3.5 * math.sin(
                    2.0 * math.pi * elapsed_days / 70.0 + occupancy_phase[key]
                )
                shock = float(rng.normal(0.0, 1.15))
                if rng.random() < 0.035:
                    shock += float(rng.normal(0.0, 3.5))
                occupancy_state[key] = (
                    0.90 * occupancy_state[key] + 0.10 * slow_target + shock
                )
                occupancy_state[key] = _clip(
                    occupancy_state[key], config.resident_min, config.resident_max
                )
                total_residents = int(round(occupancy_state[key]))
                variant_counts = _variant_counts(total_residents, rng)
                area_effect = loc_effect[key]

                # Daily variation is shared by many menu items, creating visible peaks and troughs.
                daily_site_shock = float(rng.normal(0.0, 0.050))
                if rng.random() < 0.045:
                    daily_site_shock += float(rng.normal(0.0, 0.085))

                for item in day_rows:
                    variant = item["menu_variant"]
                    variant_residents = int(
                        variant_counts.get(variant, max(1, round(total_residents * 0.1)))
                    )
                    label = item["menu_label"]
                    # Some workbook rows are service headings rather than actual foods.
                    # Keep them in the menu reference, but do not create item-level ML targets from them.
                    if _generic_service_label(label):
                        continue
                    category = item["category"] or "Uncategorised"
                    component = item["component"]
                    meal = item["meal_service"]

                    stable_preference = 0.18 + 0.64 * _stable01(
                        f"pref|{config.seed}|{label}|{variant}"
                    )
                    item_phase = 2.0 * math.pi * _stable01(
                        f"pref-phase|{config.seed}|{label}|{variant}"
                    )
                    # Preferences drift over several menu cycles rather than being fixed forever.
                    preference = stable_preference + 0.055 * math.sin(
                        2.0 * math.pi * elapsed_days / 56.0 + item_phase
                    ) + float(rng.normal(0.0, 0.025))
                    if rng.random() < 0.018:
                        preference += float(rng.normal(0.0, 0.085))
                    preference = _clip(preference, 0.08, 0.92)

                    expected_participation = _participation(
                        component, category, stable_preference
                    )
                    actual_participation = _participation(
                        component, category, preference
                    )

                    recipe_serving = (
                        float(item["serving_size_g"]) / 1000.0
                        if item.get("serving_size_g") is not None
                        and float(item["serving_size_g"]) > 0
                        else None
                    )
                    portion = _portion_kg(category, component, recipe_serving, label)

                    # What the kitchen plans can use predictable menu/calendar context, but not every
                    # real-day shock.  This prevents the preparation target being a near-perfect formula.
                    known_calendar = seasonal * weekend * area_effect
                    planned_consumers = (
                        variant_residents * expected_participation * known_calendar
                    )
                    plan_noise = float(rng.normal(0.0, 0.065))
                    if rng.random() < 0.025:
                        plan_noise += float(rng.normal(0.0, 0.10))
                    buffer = _prep_buffer(component, variant, expected_participation)
                    prepared_kg = max(
                        0.05,
                        planned_consumers * portion * (1.0 + buffer) * (1.0 + plan_noise),
                    )

                    # Actual demand contains weekly, daily, meal and preference shocks that are not
                    # fully knowable in advance, which makes the synthetic series less mechanical.
                    service_shock = (
                        weekly_site_shock.get(key, 0.0)
                        + weekly_meal_shock.get(meal, 0.0)
                        + daily_site_shock
                    )
                    realised_factor = _clip(1.0 + service_shock, 0.72, 1.25)
                    consumers = (
                        variant_residents
                        * actual_participation
                        * known_calendar
                        * realised_factor
                        * (1.0 + float(rng.normal(0.0, 0.035)))
                    )
                    consumers = _clip(consumers, 0.25, variant_residents * 1.03)
                    demand_kg = max(
                        0.02,
                        consumers * portion * (1.0 + float(rng.normal(0.0, 0.025))),
                    )

                    # Served food cannot exceed what was prepared.  Under-preparation therefore
                    # produces zero production waste instead of a negative waste quantity.
                    served_kg = min(demand_kg, prepared_kg)
                    prod_waste = max(0.0, prepared_kg - served_kg)
                    prod_ratio = prod_waste / prepared_kg if prepared_kg > 0 else 0.0

                    plate_ratio = _plate_waste_ratio(
                        category, variant, meal, preference, service_shock, rng
                    )
                    plate_waste = served_kg * plate_ratio

                    # No fake supplier/order history. Use a confirmed manual cost only when one exists.
                    cost_row = c.execute(
                        "SELECT manual_cost_per_kg FROM food_items WHERE id=?", (item["food_item_id"],)
                    ).fetchone()
                    cost = float(cost_row[0]) if cost_row and cost_row[0] is not None else None

                    prod_reason = (
                        "Synthetic: demand below preparation plan"
                        if prod_ratio >= 0.08
                        else "Synthetic: normal preparation variance"
                    )
                    plate_reason = (
                        "Synthetic: low meal acceptance / leftovers"
                        if plate_ratio >= 0.20
                        else "Synthetic: normal plate leftovers"
                    )
                    notes = (
                        f"SYNTHETIC_ML run={run_id}; Harbison menu-aligned realism model; "
                        f"seed={config.seed}"
                    )

                    common = (
                        now,
                        service_date.isoformat(),
                        loc["facility_id"],
                        loc["service_area_id"],
                        meal_ids[meal],
                        item["food_item_id"],
                    )
                    rows_to_insert.append(common + (
                        "Production Waste",
                        round(prepared_kg, 3),
                        round(served_kg, 3),
                        round(prod_waste, 3),
                        round(prod_ratio * 100.0, 2),
                        cost,
                        round(prod_waste * cost, 2) if cost is not None else None,
                        prod_reason,
                        variant_residents,
                        notes,
                        None,
                        variant,
                        component,
                        run_id,
                    ))
                    rows_to_insert.append(common + (
                        "Plate Waste",
                        round(prepared_kg, 3),
                        round(served_kg, 3),
                        round(plate_waste, 3),
                        round(plate_ratio * 100.0, 2),
                        cost,
                        round(plate_waste * cost, 2) if cost is not None else None,
                        plate_reason,
                        variant_residents,
                        notes,
                        None,
                        variant,
                        component,
                        run_id,
                    ))
                    menu_rows_used += 1

                    if len(rows_to_insert) >= 5000:
                        c.executemany(insert_sql, rows_to_insert)
                        rows_to_insert.clear()

        if rows_to_insert:
            c.executemany(insert_sql, rows_to_insert)

        tx_count = c.execute(
            "SELECT COUNT(*) FROM transactions WHERE synthetic_run_id=?", (run_id,)
        ).fetchone()[0]
        c.execute(
            "UPDATE synthetic_generation_runs SET menu_rows_used=?,transactions_created=? WHERE id=?",
            (menu_rows_used, tx_count, run_id),
        )

        distinct_foods = c.execute(
            "SELECT COUNT(DISTINCT food_item_id) FROM transactions WHERE synthetic_run_id=?", (run_id,)
        ).fetchone()[0]

    return {
        "run_id": int(run_id),
        "transactions": int(tx_count),
        "menu_rows_used": int(menu_rows_used),
        "days": (config.end_date - config.start_date).days + 1,
        "locations": len(locations),
        "distinct_foods": int(distinct_foods),
        "seed": int(config.seed),
        "created_fallback_locations": bool(created_fallback),
    }



def clear_synthetic_ml_data() -> int:
    with connection() as c:
        count = c.execute("SELECT COUNT(*) FROM transactions WHERE synthetic_run_id IS NOT NULL").fetchone()[0]
        c.execute("DELETE FROM transactions WHERE synthetic_run_id IS NOT NULL")
        c.execute("DELETE FROM synthetic_generation_runs")
    return int(count)



def synthetic_summary() -> dict:
    with connection() as c:
        tx = c.execute("SELECT COUNT(*) FROM transactions WHERE synthetic_run_id IS NOT NULL").fetchone()[0]
        runs = c.execute("SELECT COUNT(*) FROM synthetic_generation_runs").fetchone()[0]
        d = c.execute(
            """SELECT MIN(service_date),MAX(service_date),COUNT(DISTINCT food_item_id),COUNT(DISTINCT service_date),
                      COUNT(DISTINCT facility_id),COUNT(DISTINCT service_area_id)
               FROM transactions WHERE synthetic_run_id IS NOT NULL"""
        ).fetchone()
    return {
        "transactions": int(tx),
        "runs": int(runs),
        "start_date": d[0] if d and d[0] else None,
        "end_date": d[1] if d and d[1] else None,
        "foods": int(d[2] or 0) if d else 0,
        "days": int(d[3] or 0) if d else 0,
        "facilities": int(d[4] or 0) if d else 0,
        "service_areas": int(d[5] or 0) if d else 0,
    }
