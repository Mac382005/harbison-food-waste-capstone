from __future__ import annotations

from datetime import datetime

from .db import execute, fetchone, fetchall, connection
from .auth import seed_demo_users


FACILITIES = {
    "Harbison Facility A": ["Main Dining", "North Dining", "South Dining", "Memory Support"],
    "Harbison Facility B": ["Main Dining", "East Dining", "West Dining", "Memory Support"],
}
MEALS = ["Breakfast", "Morning Tea", "Lunch", "Afternoon Tea", "Dinner", "Snacks"]
FOODS = [
    ("Porridge", "Cereal", 3.50),
    ("Corn Flakes", "Cereal", 4.20),
    ("Bread/Rolls/Toast", "Bakery", 5.50),
    ("Pancakes", "Bakery", 6.80),
    ("Scrambled Eggs", "Eggs and Dairy", 10.00),
    ("Yoghurt", "Eggs and Dairy", 7.20),
    ("Fruit Salad", "Fruit/Veg/Salad", 8.00),
    ("Vegetable Soup", "Soup", 5.40),
    ("Chicken Casserole", "Mains - Protein", 8.00),
    ("Beef Stew", "Mains - Protein", 11.50),
    ("Fish Fillet", "Mains - Protein", 12.20),
    ("Mashed Potato", "Mains - Carbohydrate", 4.10),
    ("Rice", "Mains - Carbohydrate", 3.30),
    ("Mixed Vegetables", "Mains - Vegetables", 5.20),
    ("Carrots", "Mains - Vegetables", 4.60),
    ("Apple Crumble", "Dessert", 7.50),
    ("Custard", "Dessert", 5.80),
    ("Tea/Coffee", "Beverages", 2.50),
    ("Juice", "Beverages", 3.80),
]

INGREDIENTS = [
    ("Chicken breast", "kg", "Supplier A", 10, 92.0),
    ("Beef", "kg", "Supplier A", 10, 135.0),
    ("Fish", "kg", "Supplier A", 10, 145.0),
    ("Potato", "kg", "Produce Supplier", 20, 38.0),
    ("Rice", "kg", "Dry Goods Supplier", 20, 52.0),
    ("Mixed vegetables", "kg", "Produce Supplier", 10, 36.0),
    ("Carrot", "kg", "Produce Supplier", 10, 25.0),
    ("Milk", "L", "Dairy Supplier", 12, 30.0),
    ("Egg", "each", "Dairy Supplier", 180, 72.0),
    ("Flour", "kg", "Dry Goods Supplier", 12, 24.0),
    ("Sugar", "kg", "Dry Goods Supplier", 15, 30.0),
    ("Stock/Sauce base", "kg", "Dry Goods Supplier", 5, 32.0),
]

RECIPE_MAP = {
    "Chicken Casserole": (20.0, [("Chicken breast", 10.0), ("Carrot", 3.0), ("Mixed vegetables", 4.0), ("Stock/Sauce base", 1.5)]),
    "Beef Stew": (20.0, [("Beef", 10.0), ("Carrot", 3.0), ("Potato", 5.0), ("Stock/Sauce base", 1.2)]),
    "Fish Fillet": (10.0, [("Fish", 9.0), ("Flour", 0.7)]),
    "Mashed Potato": (20.0, [("Potato", 17.0), ("Milk", 2.0)]),
    "Rice": (20.0, [("Rice", 8.0)]),
    "Mixed Vegetables": (10.0, [("Mixed vegetables", 10.0)]),
    "Carrots": (10.0, [("Carrot", 10.0)]),
    "Scrambled Eggs": (10.0, [("Egg", 60.0), ("Milk", 2.0)]),
}


def get_id(table, name):
    r = fetchone(f"SELECT id FROM {table} WHERE name=?", (name,))
    return r["id"] if r else None


def seed_all():
    seed_demo_users()
    for facility, areas in FACILITIES.items():
        execute("INSERT OR IGNORE INTO facilities(name) VALUES(?)", (facility,))
        fid = get_id("facilities", facility)
        for area in areas:
            execute("INSERT OR IGNORE INTO service_areas(facility_id,name) VALUES(?,?)", (fid, area))

    for i, meal in enumerate(MEALS):
        execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,?)", (meal, i))

    for _, cat, _ in FOODS:
        execute("INSERT OR IGNORE INTO food_categories(name) VALUES(?)", (cat,))

    for food, cat, cost in FOODS:
        cid = get_id("food_categories", cat)
        execute(
            "INSERT OR IGNORE INTO food_items(name,category_id,manual_cost_per_kg) VALUES(?,?,?)",
            (food, cid, cost),
        )

    admin = fetchone("SELECT id FROM users WHERE username='admin'")
    for name, unit, supplier, qty, price in INGREDIENTS:
        execute("INSERT OR IGNORE INTO ingredients(name,base_unit,supplier) VALUES(?,?,?)", (name, unit, supplier))
        iid = get_id("ingredients", name)
        if not fetchone("SELECT id FROM ingredient_price_history WHERE ingredient_id=? LIMIT 1", (iid,)):
            execute(
                """INSERT INTO ingredient_price_history(
                ingredient_id,effective_date,pack_quantity,pack_unit,purchase_price,unit_cost,recorded_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (iid, "2026-08-01", qty, unit, price, price/qty, admin["id"] if admin else None, datetime.now().isoformat(timespec="seconds")),
            )

    for food_name, (yield_kg, ingredients) in RECIPE_MAP.items():
        fid = get_id("food_items", food_name)
        if fid is None:
            continue
        if not fetchone("SELECT id FROM recipes WHERE food_item_id=?", (fid,)):
            rid = execute("INSERT INTO recipes(food_item_id,yield_kg,notes) VALUES(?,?,?)", (fid, yield_kg, "Seeded prototype recipe"))
        else:
            rid = fetchone("SELECT id FROM recipes WHERE food_item_id=?", (fid,))["id"]
        for ing_name, qty in ingredients:
            iid = get_id("ingredients", ing_name)
            unit = fetchone("SELECT base_unit FROM ingredients WHERE id=?", (iid,))["base_unit"]
            execute(
                "INSERT OR IGNORE INTO recipe_ingredients(recipe_id,ingredient_id,quantity,unit) VALUES(?,?,?,?)",
                (rid, iid, qty, unit),
            )

    if not fetchone("SELECT id FROM menu_schedule LIMIT 1"):
        seed_menu()


def seed_menu():
    meal_ids = {r["name"]: r["id"] for r in fetchall("SELECT * FROM meals")}
    food_ids = {r["name"]: r["id"] for r in fetchall("SELECT * FROM food_items")}

    breakfast = ["Porridge", "Bread/Rolls/Toast", "Scrambled Eggs", "Yoghurt", "Fruit Salad", "Tea/Coffee"]
    tea = ["Tea/Coffee", "Juice", "Bread/Rolls/Toast", "Fruit Salad"]
    lunch_templates = [
        ["Vegetable Soup", "Chicken Casserole", "Mashed Potato", "Mixed Vegetables", "Apple Crumble", "Custard"],
        ["Vegetable Soup", "Beef Stew", "Rice", "Carrots", "Apple Crumble", "Custard"],
        ["Vegetable Soup", "Fish Fillet", "Mashed Potato", "Mixed Vegetables", "Apple Crumble", "Custard"],
        ["Vegetable Soup", "Chicken Casserole", "Rice", "Carrots", "Apple Crumble", "Custard"],
    ]
    dinner_templates = [
        ["Vegetable Soup", "Beef Stew", "Mashed Potato", "Mixed Vegetables", "Custard"],
        ["Vegetable Soup", "Chicken Casserole", "Rice", "Carrots", "Custard"],
        ["Vegetable Soup", "Fish Fillet", "Mashed Potato", "Mixed Vegetables", "Custard"],
        ["Vegetable Soup", "Beef Stew", "Rice", "Carrots", "Custard"],
    ]
    with connection() as c:
        for week in range(1, 5):
            for dow in range(7):
                schedule = {
                    "Breakfast": breakfast,
                    "Morning Tea": tea,
                    "Lunch": lunch_templates[(week + dow) % 4],
                    "Afternoon Tea": tea,
                    "Dinner": dinner_templates[(week + dow + 1) % 4],
                    "Snacks": ["Yoghurt", "Fruit Salad", "Juice"],
                }
                for meal_name, foods in schedule.items():
                    for food in foods:
                        c.execute(
                            "INSERT OR IGNORE INTO menu_schedule(week_number,day_of_week,meal_id,food_item_id) VALUES(?,?,?,?)",
                            (week, dow, meal_ids[meal_name], food_ids[food]),
                        )
