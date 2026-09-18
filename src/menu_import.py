from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from .db import APP_DIR, connection

MENU_FILE = APP_DIR / "data" / "private" / "reference" / "harbison_menu_autumn_winter_2026.csv"


def _clean_menu_label(value: str) -> str:
    text = (value or "").strip()
    # Some decorative food icons in the source workbook were exported as '?'
    # characters. Remove them so menu names stay clean and readable.
    text = text.replace("?", "")
    text = re.sub(r"\s*\*+\s*$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,;:])", r"\1", text)
    return text.strip()


def import_harbison_menu(path: Path = MENU_FILE) -> int:
    if not path.exists():
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f, connection() as c:
        c.execute("DELETE FROM harbison_menu_schedule")
        c.execute("DELETE FROM menu_item_recipe_links")
        for row in csv.DictReader(f):
            label = _clean_menu_label(row.get("menu_label") or "")
            if not label:
                continue
            category = (row.get("category") or "Uncategorised").strip() or "Uncategorised"
            c.execute("INSERT OR IGNORE INTO food_categories(name) VALUES(?)", (category,))
            category_id = c.execute("SELECT id FROM food_categories WHERE name=?", (category,)).fetchone()[0]
            c.execute(
                """INSERT INTO food_items(name,category_id,manual_cost_per_kg,active)
                   VALUES(?,?,NULL,1)
                   ON CONFLICT(name) DO UPDATE SET category_id=excluded.category_id,active=1""",
                (label, category_id),
            )
            food_item_id = c.execute("SELECT id FROM food_items WHERE name=?", (label,)).fetchone()[0]

            linked_recipe = (row.get("linked_recipe") or "").strip() or None
            linked_recipe_food_item_id = None
            if linked_recipe:
                rr = c.execute(
                    """SELECT fi.id FROM sponsor_recipes sr
                       JOIN food_items fi ON fi.id=sr.food_item_id
                       WHERE lower(sr.recipe_name)=lower(?)""",
                    (linked_recipe,),
                ).fetchone()
                if rr:
                    linked_recipe_food_item_id = rr[0]
                    c.execute(
                        """INSERT INTO menu_item_recipe_links(menu_food_item_id,recipe_food_item_id)
                           VALUES(?,?) ON CONFLICT(menu_food_item_id) DO UPDATE SET recipe_food_item_id=excluded.recipe_food_item_id""",
                        (food_item_id, linked_recipe_food_item_id),
                    )

            c.execute(
                """INSERT OR IGNORE INTO harbison_menu_schedule(
                    menu_variant,week_number,day_of_week,day_name,meal_service,component,
                    menu_label,food_item_id,linked_recipe_name,linked_recipe_food_item_id,
                    category,source_sheet,source_document,imported_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    (row.get("menu_variant") or "Regular").strip(),
                    int(row.get("week_number") or 1),
                    int(row.get("day_of_week") or 0),
                    (row.get("day_name") or "").strip(),
                    (row.get("meal_service") or "").strip(),
                    (row.get("component") or "").strip(),
                    label,
                    food_item_id,
                    linked_recipe,
                    linked_recipe_food_item_id,
                    category,
                    (row.get("source_sheet") or "").strip() or None,
                    (row.get("source_document") or "").strip() or None,
                    now,
                ),
            )
            count += 1
    return count


def ensure_menu_loaded() -> int:
    with connection() as c:
        n = c.execute("SELECT COUNT(*) FROM harbison_menu_schedule").fetchone()[0]
    if n:
        return n
    return import_harbison_menu()
