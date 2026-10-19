"""Synthetic data for Resident Meal & Consumption Records.

Everything generated here is labelled data_source='fictional_demo'. Resident codes are invented
(DEMO-...), orders are built from the four-week menu plus common extras, and the consumption
percentages are illustrative values for software testing. They are not Harbison outcomes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np

from .db import connection, fetchall, fetchone
from .intake import MISSED_REASONS, PLATE_MEALS, UNEATEN_REASONS, menu_components_for_meal, standard_plate
from .resident_choices import (BREAKFAST_EXTRAS, MELTING_TREATS, TEA_DRINKS, TEA_SNACKS, choice_item,
                              ensure_soup_items, soup_of_the_day)
from .textures import NO_MELTING_DESSERTS, TEXTURES, texture_label

MEAL_TIMES = {"Breakfast": time(8, 15), "Morning Tea": time(10, 15), "Lunch": time(12, 30),
              "Afternoon Tea": time(15, 0), "Dinner": time(17, 30)}
MEAL_SHIFT = {"Breakfast": 4.0, "Morning Tea": 6.0, "Lunch": 0.0, "Afternoon Tea": 6.0, "Dinner": -4.0}
FIRST_NAMES = ["Margaret", "Dorothy", "Joan", "Betty", "Shirley", "Patricia", "Barbara", "Valerie", "Maureen",
               "Jean", "Beryl", "Gwen", "Edna", "Mavis", "Elsie", "Irene", "June", "Noreen", "Rosemary", "Judith",
               "Robert", "John", "William", "Kenneth", "Ronald", "Keith", "Graham", "Barry", "Colin", "Leslie",
               "Arthur", "Frank", "Harold", "Norman", "Raymond", "Trevor", "Bruce", "Neville", "Stanley", "Alan"]
LAST_NAMES = ["Abbott", "Barlow", "Carmody", "Dawson", "Ellery", "Fletcher", "Garnett", "Halloran", "Ingram",
              "Jessop", "Kerrigan", "Lomax", "Mayhew", "Nolan", "Oakes", "Prentice", "Quinlan", "Rowe", "Sutcliffe",
              "Tolley", "Upton", "Vickery", "Whitlock", "Yardley"]
REASON_WEIGHTS = np.array([5, 4, 2, 3, 1, 2, 1, 1, 1, 1, 1], dtype=float)


GENERATED = "SELECT id FROM intake_residents WHERE data_source='fictional_demo' AND resident_code LIKE 'DEMO-%'"


def clear_synthetic_resident_data():
    """Remove generated demo residents and their records. Uploaded residents are left alone."""
    obs = f"SELECT id FROM intake_meal_observations WHERE resident_id IN ({GENERATED})"
    with connection() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "intake_clinical_reviews" in tables:  # left over from an earlier version
            c.execute(f"DELETE FROM intake_clinical_reviews WHERE resident_id IN ({GENERATED})")
        c.execute(f"DELETE FROM intake_component_observations WHERE observation_id IN ({obs})")
        c.execute(f"DELETE FROM transactions WHERE intake_observation_id IN ({obs})")
        c.execute(f"DELETE FROM intake_meal_observations WHERE resident_id IN ({GENERATED})")
        c.execute(f"DELETE FROM intake_meal_orders WHERE resident_id IN ({GENERATED})")
        c.execute(f"DELETE FROM intake_residents WHERE id IN ({GENERATED})")


def _nearest_pct(value: float) -> int:
    return int(min((0, 25, 50, 75, 100), key=lambda p: abs(p - value)))


def _pick(rng, names: list[str]) -> dict:
    return choice_item(str(rng.choice(names)))


def _menu_week_fn():
    """Menu-week calculator read once up front, so no extra connection is opened while writing."""
    s = fetchone("SELECT cycle_start_date,cycle_weeks FROM menu_settings WHERE id=1")
    start, weeks = date.fromisoformat(s["cycle_start_date"]), int(s["cycle_weeks"])
    return lambda d: ((d - start).days // 7) % weeks + 1


def _load_menus(first: date, last: date, variants: list[str], week_of) -> dict:
    """Menu items for every (weekday, menu week, meal, variant) in the date range."""
    cache: dict = {}
    d = first
    while d <= last and len(cache) < 7 * 4 * 3 * max(1, len(variants)):
        for meal in ("Breakfast", "Lunch", "Dinner"):
            for variant in variants:
                cache.setdefault((d.weekday(), week_of(d), meal, variant),
                                 menu_components_for_meal(d, meal, variant))
        d += timedelta(days=1)
    return cache


TEXTURE_SHARES = {"Regular": 0.6, "Soft Bite Sized": 0.2, "Minced": 0.1, "Puree": 0.1}


def build_order(rng, d: date, meal: str, variant: str, menu_cache: dict, week: int,
                soup_ids: dict | None = None) -> list[dict]:
    """What a synthetic resident orders for one meal: menu food plus soup, drinks, desserts and snacks
    chosen from the Harbison supplier list."""
    menu = menu_cache.get((d.weekday(), week, meal, variant), [])
    melt_ok = variant not in NO_MELTING_DESSERTS
    items: list[dict] = []
    def choose(options):
        # mostly the first choice (Main Choice 1 / continental), sometimes the alternatives
        weights = [0.65] + [0.35 / (len(options) - 1)] * (len(options) - 1) if len(options) > 1 else [1.0]
        return options[int(rng.choice(len(options), p=weights))]

    if meal == "Breakfast":
        items += standard_plate(menu, meal, choose)
        if rng.random() < 0.3:
            items.append(_pick(rng, BREAKFAST_EXTRAS))
        items.append(choice_item("Pineapple juice") if rng.random() < 0.5 else _pick(rng, ["Tea", "Coffee"]))
    elif meal in ("Morning Tea", "Afternoon Tea"):
        items.append(_pick(rng, TEA_DRINKS))
        roll = rng.random()
        if melt_ok and meal == "Afternoon Tea" and roll < 0.3:
            items.append(_pick(rng, MELTING_TREATS))
        elif roll < 0.8:
            items.append(_pick(rng, TEA_SNACKS))
    else:
        plate = standard_plate(menu, meal, choose)
        has_menu_soup = any(m["component_group"] == "soup" for m in plate)
        if not has_menu_soup and rng.random() < (0.3 if meal == "Lunch" else 0.65):
            soup = soup_of_the_day(d, meal)
            label = soup + (f" ({texture_label(variant)})" if variant in NO_MELTING_DESSERTS else "")
            items.append({"food_item_id": (soup_ids or {}).get(soup), "item_label": label, "component_group": "soup"})
        elif has_menu_soup and rng.random() < 0.35:
            plate = [m for m in plate if m["component_group"] != "soup"]  # not everyone has the evening soup
        items += [m for m in plate if m["component_group"] != "dessert"]
        desserts = [m for m in plate if m["component_group"] == "dessert"]
        roll = rng.random()
        if desserts and (roll < 0.6 or not melt_ok):
            items += desserts[:1]
        elif melt_ok and roll < 0.85:
            items.append(_pick(rng, MELTING_TREATS))
        else:
            items.append(_pick(rng, ["Pavlova", "Vanilla custard", "Fruit salad"]))
        if rng.random() < 0.5:
            items.append(_pick(rng, ["Cordial", "Pineapple juice", "Diet cordial"]))
    seen, unique = set(), []
    for it in items:
        if it["item_label"] not in seen:
            seen.add(it["item_label"])
            unique.append(it)
    return unique



STANDARD_SERVED_G = {"protein": 180, "carbohydrate": 120, "vegetables": 80, "soup": 250,
                     "dessert": 120, "drinks": 200, "other": 120}

def _demo_served_weight_g(c, item, rng):
    base = None
    if item.get("food_item_id"):
        row = c.execute("SELECT serving_size_g FROM sponsor_recipes WHERE food_item_id=? ORDER BY id DESC LIMIT 1",
                        (item["food_item_id"],)).fetchone()
        if row and row[0]:
            base = float(row[0])
    if base is None:
        base = float(STANDARD_SERVED_G.get(item.get("component_group"), 120))
    return round(max(15.0, base * float(rng.normal(1.0, 0.08))), 1)


def generate_synthetic_resident_data(start: date, end: date, residents_per_area: int = 12, seed: int = 42,
                         orders_until: date | None = None) -> dict:
    """Create synthetic residents, their meal orders from start to orders_until (default today),
    and consumption records from start to end (default: up to yesterday)."""
    if end < start:
        raise ValueError("End date must be on or after start date.")
    orders_until = max(orders_until or date.today(), end)
    locations = fetchall(
        """SELECT f.id facility_id, sa.id service_area_id FROM facilities f
           JOIN service_areas sa ON sa.facility_id=f.id
           WHERE f.active=1 AND sa.active=1 ORDER BY f.id, sa.id"""
    )
    if not locations:
        raise RuntimeError("Add at least one facility and dining area in Menu & Locations first.")
    if not fetchall("SELECT 1 FROM harbison_menu_schedule LIMIT 1"):
        raise RuntimeError("No menu is loaded. Import the four-week menu first.")

    clear_synthetic_resident_data()
    rng = np.random.default_rng(seed)
    variants = list(TEXTURES)
    care_user = fetchall("SELECT id FROM users WHERE role='care' AND active=1 ORDER BY id LIMIT 1")
    recorder = care_user[0]["id"] if care_user else None
    meal_ids = {r["name"]: r["id"] for r in fetchall("SELECT id,name FROM meals")}
    now = datetime.now().isoformat(timespec="seconds")
    total_days = (end - start).days + 1
    decline_start = max(0, total_days - 21)
    week_of = _menu_week_fn()
    menu_cache = _load_menus(start, orders_until, variants, week_of)
    soup_ids = ensure_soup_items()
    item_effect: dict = {}
    counts = {"residents": 0, "orders": 0, "meals_recorded": 0, "items_recorded": 0}

    with connection() as c:
        residents_generated = []
        names = [f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES]
        names = [names[i] for i in rng.permutation(len(names))]
        for area_idx, loc in enumerate(locations):
            for n in range(1, residents_per_area + 1):
                variant = str(rng.choice(list(TEXTURE_SHARES), p=list(TEXTURE_SHARES.values())))
                room = str((area_idx + 1) * 100 + n)
                cur = c.execute(
                    """INSERT INTO intake_residents(resident_code,facility_id,service_area_id,menu_variant,room,
                           display_name,data_source,active,created_at,created_by)
                       VALUES(?,?,?,?,?,?,'fictional_demo',1,?,NULL)""",
                    (f"DEMO-{loc['service_area_id']:02d}-{n:03d}", loc["facility_id"], loc["service_area_id"],
                     variant, room, names[len(residents_generated)], now),
                )
                residents_generated.append({"id": cur.lastrowid, **loc, "variant": variant,
                                 "appetite": float(np.clip(rng.normal(76, 11), 35, 96)),
                                 "declining": rng.random() < 0.12})
        counts["residents"] = len(residents_generated)

        day = start
        while day <= orders_until:
            day_idx = (day - start).days
            week = week_of(day)
            record = day <= end
            for pt in residents_generated:
                for meal in PLATE_MEALS:
                    if meal not in meal_ids:
                        continue
                    order = build_order(rng, day, meal, pt["variant"], menu_cache, week, soup_ids)
                    for it in order:
                        c.execute(
                            """INSERT OR IGNORE INTO intake_meal_orders(resident_id,service_date,meal_id,item_label,
                                   component_group,food_item_id,data_source,ordered_by,ordered_at)
                               VALUES(?,?,?,?,?,?,'fictional_demo',NULL,?)""",
                            (pt["id"], day.isoformat(), meal_ids[meal], it["item_label"], it["component_group"],
                             it["food_item_id"], now),
                        )
                        counts["orders"] += 1
                    if not record:  # today stays open for nurses; every past meal is recorded
                        continue
                    appetite = pt["appetite"] + MEAL_SHIFT.get(meal, 0.0)
                    if pt["declining"] and day_idx >= decline_start:
                        appetite -= 30 * (day_idx - decline_start + 1) / 21
                    roll = rng.random()
                    refuse_p = 0.02 + (0.08 if pt["declining"] and day_idx >= decline_start else 0.0)
                    status = "missed" if roll < 0.02 else "refused" if roll < 0.02 + refuse_p else "served"
                    cur = c.execute(
                        """INSERT INTO intake_meal_observations(
                               resident_id,service_date,meal_id,facility_id,service_area_id,menu_variant,menu_week,
                               meal_status,missed_reason,replacement_description,staff_observation,data_source,
                               version,supersedes_id,is_current,correction_reason,recorded_by,recorded_at)
                           VALUES(?,?,?,?,?,?,?,?,?,NULL,NULL,'fictional_demo',1,NULL,1,NULL,?,?)""",
                        (pt["id"], day.isoformat(), meal_ids[meal], pt["facility_id"], pt["service_area_id"],
                         pt["variant"], week, status,
                         str(rng.choice(MISSED_REASONS[:-1])) if status == "missed" else None, recorder,
                         (datetime.combine(day, MEAL_TIMES[meal]) + timedelta(minutes=40)).isoformat(timespec="seconds")),
                    )
                    counts["meals_recorded"] += 1
                    if status != "served":
                        continue
                    for it in order:
                        effect = item_effect.setdefault(it["item_label"], float(rng.normal(0, 8)))
                        u = rng.random()
                        if u < 0.04:
                            observed, pct, reason = "not_observed", None, None
                        else:
                            observed = "observed"
                            pct = _nearest_pct(appetite + effect + rng.normal(0, 18))
                            reason = None
                            if pct <= 50 and rng.random() < 0.7:
                                reason = str(rng.choice(UNEATEN_REASONS, p=REASON_WEIGHTS / REASON_WEIGHTS.sum()))
                        c.execute(
                            """INSERT INTO intake_component_observations(observation_id,component_group,food_item_id,
                                   item_label,observed_status,intake_pct,served_weight_g,reason_uneaten,reason_other)
                               VALUES(?,?,?,?,?,?,?,?,NULL)""",
                            (cur.lastrowid, it["component_group"], it["food_item_id"], it["item_label"],
                             observed, pct, _demo_served_weight_g(c, it, rng), reason),
                        )
                        counts["items_recorded"] += 1
            day += timedelta(days=1)
        c.execute("INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
                  (now, None, "INTAKE_DEMO_GENERATED", str(counts)))
    return counts
