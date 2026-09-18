from __future__ import annotations
from datetime import date
from .db import fetchone, fetchall


def menu_week(d: date):
    s = fetchone("SELECT cycle_start_date,cycle_weeks FROM menu_settings WHERE id=1")
    start = date.fromisoformat(s["cycle_start_date"])
    weeks = int(s["cycle_weeks"])
    return ((d - start).days // 7) % weeks + 1


def menu_variants(d: date, meal_service: str | None = None):
    sql = "SELECT DISTINCT menu_variant FROM harbison_menu_schedule WHERE week_number=? AND day_of_week=?"
    params = [menu_week(d), d.weekday()]
    if meal_service:
        sql += " AND meal_service=?"
        params.append(meal_service)
    sql += " ORDER BY CASE menu_variant WHEN 'Regular' THEN 1 WHEN 'Soft Bite Sized' THEN 2 WHEN 'Minced' THEN 3 WHEN 'Puree' THEN 4 ELSE 9 END"
    return [r["menu_variant"] for r in fetchall(sql, tuple(params))]


def menu_services(d: date, variant: str):
    rows = fetchall(
        """SELECT DISTINCT meal_service FROM harbison_menu_schedule
           WHERE week_number=? AND day_of_week=? AND menu_variant=?
           ORDER BY CASE meal_service WHEN 'Breakfast' THEN 1 WHEN 'Morning Tea' THEN 2 WHEN 'Lunch' THEN 3 WHEN 'Afternoon Tea' THEN 4 WHEN 'Dinner' THEN 5 ELSE 9 END""",
        (menu_week(d), d.weekday(), variant),
    )
    return [r["meal_service"] for r in rows]


def menu_components(d: date, variant: str, meal_service: str):
    rows = fetchall(
        """SELECT DISTINCT component FROM harbison_menu_schedule
           WHERE week_number=? AND day_of_week=? AND menu_variant=? AND meal_service=?
           ORDER BY component""",
        (menu_week(d), d.weekday(), variant, meal_service),
    )
    return [r["component"] for r in rows]


def menu_items(d: date, meal_service: str, variant: str = "Regular", component: str | None = None):
    sql = """SELECT hms.food_item_id id,hms.menu_label name,hms.category,hms.component,
                    hms.linked_recipe_name,hms.linked_recipe_food_item_id
             FROM harbison_menu_schedule hms
             WHERE hms.week_number=? AND hms.day_of_week=? AND hms.menu_variant=? AND hms.meal_service=?"""
    params = [menu_week(d), d.weekday(), variant, meal_service]
    if component and component != "All components":
        sql += " AND hms.component=?"
        params.append(component)
    sql += " ORDER BY hms.component,hms.menu_label"
    return fetchall(sql, tuple(params))
