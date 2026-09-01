from __future__ import annotations
from datetime import date
from .db import fetchone, fetchall


def menu_week(d: date):
    s = fetchone("SELECT cycle_start_date,cycle_weeks FROM menu_settings WHERE id=1")
    start = date.fromisoformat(s["cycle_start_date"])
    weeks = int(s["cycle_weeks"])
    return ((d - start).days // 7) % weeks + 1


def menu_items(d: date, meal_id: int):
    return fetchall(
        """SELECT fi.id,fi.name,fi.manual_cost_per_kg,fc.name category
           FROM menu_schedule ms
           JOIN food_items fi ON fi.id=ms.food_item_id
           LEFT JOIN food_categories fc ON fc.id=fi.category_id
           WHERE ms.week_number=? AND ms.day_of_week=? AND ms.meal_id=? AND fi.active=1
           ORDER BY fc.name,fi.name""",
        (menu_week(d), d.weekday(), meal_id),
    )
