from __future__ import annotations

from .db import execute, fetchone
from .auth import seed_demo_users

# These are generic service labels, not fabricated food/recipe data.
# Real facility/service-area names should be configured in Menu & Locations.
MEALS = ["Breakfast", "Morning Tea", "Lunch", "Afternoon Tea", "Dinner", "Snacks"]


def seed_core():
    """Create only the minimum application structure.

    Sponsor-first mode intentionally does NOT seed made-up foods, ingredients,
    recipes, menu schedules, prices or waste transactions.
    """
    seed_demo_users()
    for i, meal in enumerate(MEALS):
        execute("INSERT OR IGNORE INTO meals(name,sort_order) VALUES(?,?)", (meal, i))

    # Keep the menu settings table valid, but do not invent a menu schedule.
    if not fetchone("SELECT id FROM menu_settings WHERE id=1"):
        execute(
            "INSERT INTO menu_settings(id,cycle_start_date,cycle_weeks) VALUES(1,'2026-08-03',4)"
        )


# Backward-compatible name for any old imports. It now behaves sponsor-first.
def seed_all():
    seed_core()
