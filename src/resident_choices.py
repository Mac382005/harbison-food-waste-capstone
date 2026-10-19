"""Items residents can choose in addition to the four-week menu.

Every item comes from the Harbison supplier comparison (products the kitchen already buys), renamed from
pack descriptions to what a resident would order. Soups come from the Harbison soup recipe file.
"""
from __future__ import annotations

import csv
from datetime import date, datetime

from .db import APP_DIR, connection

SOUPS_FILE = APP_DIR / "data" / "private" / "reference" / "harbison_soups.csv"
FALLBACK_SOUPS = ["Soup of the day"]

# (resident-facing name, component group, menu section, melts to thin liquid?)
CHOICES = [
    # Drinks
    ("Pineapple juice", "drinks", "Drinks", False),
    ("Cordial", "drinks", "Drinks", False),
    ("Diet cordial", "drinks", "Drinks", False),
    ("Tea", "drinks", "Drinks", False),
    ("Coffee", "drinks", "Drinks", False),
    ("Milo", "drinks", "Drinks", False),
    ("Skim milk", "drinks", "Drinks", False),
    ("Soy milk", "drinks", "Drinks", False),
    ("Almond milk", "drinks", "Drinks", False),
    ("Oat milk", "drinks", "Drinks", False),
    ("Lactose-free milk", "drinks", "Drinks", False),
    # Desserts
    ("Vanilla ice cream", "dessert", "Desserts", True),
    ("Chocolate ice cream", "dessert", "Desserts", True),
    ("Strawberry ice cream", "dessert", "Desserts", True),
    ("No-sugar ice cream", "dessert", "Desserts", True),
    ("Lactose-free ice cream", "dessert", "Desserts", True),
    ("Strawberry jelly", "dessert", "Desserts", True),
    ("Orange jelly", "dessert", "Desserts", True),
    ("Raspberry jelly", "dessert", "Desserts", True),
    ("Port wine jelly", "dessert", "Desserts", True),
    ("Diet jelly", "dessert", "Desserts", True),
    ("Vanilla custard", "dessert", "Desserts", False),
    ("Chocolate mousse", "dessert", "Desserts", False),
    ("Strawberry mousse", "dessert", "Desserts", False),
    ("Pannacotta", "dessert", "Desserts", False),
    ("Fruit salad", "dessert", "Desserts", False),
    ("Sliced peaches", "dessert", "Desserts", False),
    ("Pear slices", "dessert", "Desserts", False),
    ("Apricot halves", "dessert", "Desserts", False),
    ("Pavlova", "dessert", "Desserts", False),
    ("Mixed berries", "dessert", "Desserts", False),
    ("Raspberries", "dessert", "Desserts", False),
    ("Blueberries", "dessert", "Desserts", False),
    # Biscuits and snacks
    ("Biscuits", "carbohydrate", "Biscuits & snacks", False),
    ("Gluten-free biscuits", "carbohydrate", "Biscuits & snacks", False),
    ("Jatz crackers", "carbohydrate", "Biscuits & snacks", False),
    ("SAO biscuits", "carbohydrate", "Biscuits & snacks", False),
    ("Croissant", "carbohydrate", "Biscuits & snacks", False),
    ("Milk bun", "carbohydrate", "Biscuits & snacks", False),

    # Breakfast
    ("Weet-Bix", "carbohydrate", "Breakfast", False),
    ("Gluten-free Weet-Bix", "carbohydrate", "Breakfast", False),
    ("Corn Flakes", "carbohydrate", "Breakfast", False),
    ("Gluten-free Corn Flakes", "carbohydrate", "Breakfast", False),
    ("Rice Bubbles", "carbohydrate", "Breakfast", False),
    ("Sultana Bran", "carbohydrate", "Breakfast", False),
    ("Toasted muesli", "carbohydrate", "Breakfast", False),
    ("Nutri-Grain", "carbohydrate", "Breakfast", False),
    ("Hash brown", "carbohydrate", "Breakfast", False),
    ("Baked beans", "protein", "Breakfast", False),
    # Hot food
    ("Sausage roll", "protein", "Hot food", False),
    ("Party pie", "protein", "Hot food", False),
    ("Beef pie", "protein", "Hot food", False),
    ("Chicken schnitzel", "protein", "Hot food", False),
    ("Barramundi fillet", "protein", "Hot food", False),
    ("Basa fillet", "protein", "Hot food", False),
    ("Beef patty", "protein", "Hot food", False),
    ("Falafel", "protein", "Hot food", False),
    ("Chips", "carbohydrate", "Hot food", False),
]
# Which groups can be ordered at each meal. Tea times are drinks and light snacks only; breakfast items
# only at breakfast; hot food and soups only at lunch and dinner.
_MAIN = {"Today's menu", "Soups", "Hot food", "Desserts", "Drinks", "Biscuits & snacks", "Other"}
MEAL_GROUPS = {
    "Breakfast": {"Today's menu", "Breakfast", "Drinks", "Biscuits & snacks", "Other"},
    "Morning Tea": {"Drinks", "Desserts", "Biscuits & snacks", "Other"},
    "Lunch": _MAIN,
    "Afternoon Tea": {"Drinks", "Desserts", "Biscuits & snacks", "Other"},
    "Dinner": _MAIN,
}
CHOICE_BY_NAME = {name: (group, section, melts) for name, group, section, melts in CHOICES}
TEA_SNACKS = ["Biscuits", "Jatz crackers", "SAO biscuits", "Croissant", "Fruit salad", "Vanilla custard",
              "Pavlova", "Sliced peaches"]
TEA_DRINKS = ["Tea", "Coffee", "Milo", "Pineapple juice", "Cordial"]
MELTING_TREATS = ["Vanilla ice cream", "Chocolate ice cream", "Strawberry jelly", "Orange jelly", "Raspberry jelly"]
BREAKFAST_EXTRAS = ["Weet-Bix", "Corn Flakes", "Rice Bubbles", "Toasted muesli"]


def harbison_soups() -> list[dict]:
    """Soups from the Harbison recipe file (name, style, serving size); empty if the file is not present."""
    if not SOUPS_FILE.exists():
        return []
    with SOUPS_FILE.open(encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f) if r.get("soup_name")]


def soup_names() -> list[str]:
    return [s["soup_name"] for s in harbison_soups()] or FALLBACK_SOUPS


def soup_of_the_day(d: date, meal: str) -> str:
    names = soup_names()
    return names[(d.toordinal() * 2 + (1 if meal == "Dinner" else 0)) % len(names)]


def ensure_soup_items() -> dict[str, int]:
    """Make sure each Harbison soup exists as a food item with its recipe serving size (used for plate-waste kg)."""
    soups = harbison_soups()
    ids: dict[str, int] = {}
    if not soups:
        soups = [{
            "soup_name": FALLBACK_SOUPS[0],
            "style": "Standard",
            "serves": "100",
            "serving_size_g": "240",
            "yield_loss_pct": "",
            "source_page": "",
            "source_document": "Fallback menu item",
        }]
    now = datetime.now().isoformat(timespec="seconds")
    with connection() as c:
        c.execute("INSERT OR IGNORE INTO food_categories(name) VALUES('Soups')")
        cat = c.execute("SELECT id FROM food_categories WHERE name='Soups'").fetchone()[0]
        for s in soups:
            name = s["soup_name"]
            c.execute("INSERT OR IGNORE INTO food_items(name,category_id,active) VALUES(?,?,1)", (name, cat))
            fid = c.execute("SELECT id FROM food_items WHERE name=?", (name,)).fetchone()[0]
            exists = c.execute("SELECT 1 FROM sponsor_recipes WHERE recipe_name=? OR food_item_id=?",
                               (name, fid)).fetchone()
            if not exists:
                c.execute(
                    """INSERT INTO sponsor_recipes(food_item_id,recipe_name,display_name,texture,serves,serving_size_g,
                           yield_loss_pct,source_page,source_document,imported_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (fid, name, name, s.get("style"), int(s.get("serves") or 100), float(s.get("serving_size_g") or 240),
                     float(s["yield_loss_pct"]) if s.get("yield_loss_pct") else None,
                     int(s["source_page"]) if s.get("source_page") else None, s.get("source_document"), now),
                )
            ids[name] = fid
    return ids


def choice_item(name: str) -> dict:
    group = CHOICE_BY_NAME.get(name, ("other",))[0]
    return {"food_item_id": None, "item_label": name, "component_group": group}
