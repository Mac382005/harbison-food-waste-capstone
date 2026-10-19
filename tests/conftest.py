import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.db as db  # noqa: E402

MENU = [
    ("Breakfast", "Main", "Breakfast", "Porridge with Banana"),
    ("Breakfast", "Main", "Breakfast", "Scrambled Eggs"),
    ("Lunch", "Main", "Main Meals", "Roast Chicken"),
    ("Lunch", "Side", "Vegetables and Sides", "Mashed Potato"),
    ("Lunch", "Side", "Vegetables and Sides", "Steamed Broccoli"),
    ("Lunch", "Dessert", "Desserts", "Apple Crumble"),
    ("Dinner", "Main", "Soup", "Pumpkin Soup"),
    ("Dinner", "Main", "Main Meals", "Beef Casserole"),
    ("Dinner", "Dessert", "Desserts", "Custard"),
]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Fresh database with one facility, two dining areas and a small four-week menu."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with db.connection() as c:
        for i, meal in enumerate(["Breakfast", "Morning Tea", "Lunch", "Afternoon Tea", "Dinner"]):
            c.execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,?)", (meal, i))
        c.execute("INSERT INTO facilities(name) VALUES('Test Facility')")
        c.execute("INSERT INTO service_areas(facility_id,name) VALUES(1,'Area A')")
        c.execute("INSERT INTO service_areas(facility_id,name) VALUES(1,'Area B')")
        c.execute("INSERT INTO users(username,display_name,role,password_hash,created_at) "
                  "VALUES('nurse','Nurse','care','x',?)", (now,))
        for meal, comp, cat, label in MENU:
            c.execute("INSERT OR IGNORE INTO food_items(name) VALUES(?)", (label,))
            fid = c.execute("SELECT id FROM food_items WHERE name=?", (label,)).fetchone()[0]
            for week in range(1, 5):
                for dow in range(7):
                    c.execute(
                        """INSERT INTO harbison_menu_schedule(menu_variant,week_number,day_of_week,meal_service,
                               component,menu_label,food_item_id,category,imported_at)
                           VALUES('Regular',?,?,?,?,?,?,?,?)""",
                        (week, dow, meal, comp, label, fid, cat, now),
                    )
    return tmp_path / "test.db"
