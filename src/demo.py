from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from .db import fetchone, fetchall, connection
from .menu import menu_items
from .costing import food_cost_per_kg


def pct(n, d):
    if d is None or d <= 0:
        return None
    return n / d * 100.0


def generate_demo_data(days: int = 90):
    existing = fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=1")
    if existing and existing["n"] > 0:
        return 0

    random.seed(42)
    facilities = fetchall("SELECT * FROM facilities WHERE active=1")
    meal_rows = fetchall("SELECT * FROM meals ORDER BY sort_order")
    end = date.today()
    start = end - timedelta(days=days-1)
    count = 0

    with connection() as c:
        d = start
        day_index = 0
        while d <= end:
            for fac in facilities:
                areas = [dict(r) for r in c.execute(
                    "SELECT * FROM service_areas WHERE facility_id=? AND active=1 ORDER BY id",
                    (fac["id"],)
                ).fetchall()]
                for area in areas:
                    residents = 18 + ((area["id"] * 3 + day_index) % 15)
                    for meal in meal_rows:
                        items = menu_items(d, meal["id"])
                        if not items:
                            continue
                        # Exactly one menu item per area/meal/day; cycles through all available menu items over time.
                        item = items[(day_index + area["id"] + meal["id"]) % len(items)]

                        base = {
                            "Breakfast": .18,
                            "Morning Tea": .08,
                            "Lunch": .24,
                            "Afternoon Tea": .08,
                            "Dinner": .22,
                            "Snacks": .06,
                        }.get(meal["name"], .15)

                        prepared = max(.5, residents * base * random.uniform(.92, 1.12))
                        prod_rate = random.uniform(.04, .14)
                        if item["name"] in {"Fish Fillet","Beef Stew"}:
                            prod_rate += .02
                        prod_waste = min(prepared, prepared * prod_rate)
                        served = max(.1, prepared - prod_waste)

                        plate_rate = random.uniform(.05, .17)
                        if item["name"] in {"Fish Fillet","Apple Crumble"}:
                            plate_rate += random.uniform(.05, .10)
                        if random.random() < .025:
                            plate_rate += .12
                        plate_waste = min(served, served * plate_rate)

                        cost, _ = food_cost_per_kg(item["id"], d)
                        created = datetime.combine(d, datetime.min.time()).replace(hour=14).isoformat(timespec="seconds")
                        rows_to_add = [
                            ("Production Waste", prepared, served, prod_waste, pct(prod_waste, prepared),
                             random.choice(["Overproduction","Preparation/trimming waste","Quality issue","Other"])),
                            ("Plate Waste", prepared, served, plate_waste, pct(plate_waste, served),
                             random.choice(["Presented but not consumed","Quality issue","Other"])),
                        ]
                        for wt,p,s,w,wp,reason in rows_to_add:
                            c.execute(
                                """INSERT INTO transactions(
                                created_at,service_date,facility_id,service_area_id,meal_id,food_item_id,
                                waste_type,prepared_kg,served_kg,waste_kg,waste_percentage,cost_per_kg_snapshot,
                                waste_cost,waste_reason,resident_count,notes,recorded_by,is_demo)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,1)""",
                                (created,d.isoformat(),fac["id"],area["id"],meal["id"],item["id"],wt,
                                 round(p,2),round(s,2),round(w,2),wp,cost,
                                 (w*cost if cost is not None else None),reason,residents,"Synthetic demo data"),
                            )
                            count += 1
            c.commit()
            d += timedelta(days=1)
            day_index += 1
    return count
