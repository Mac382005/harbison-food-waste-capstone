from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from .db import APP_DIR, connection, fetchone

PRIVATE_REFERENCE_DIR = APP_DIR / "data" / "private" / "reference"
PRIVATE_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
SUPPLIER_FILE = PRIVATE_REFERENCE_DIR / "supplier_comparison_2025.csv"
RECIPE_FILE = PRIVATE_REFERENCE_DIR / "harbison_recipes.csv"
RECIPE_INGREDIENT_FILE = PRIVATE_REFERENCE_DIR / "harbison_recipe_ingredients.csv"

SAFE_COST_UNITS = {"kg", "L", "each"}


def _float_or_none(value):
    value = (value or "").strip()
    return None if value == "" else float(value)


def _int_or_none(value):
    value = (value or "").strip()
    return None if value == "" else int(float(value))


def sponsor_files_status():
    return {
        "supplier_file": SUPPLIER_FILE.exists(),
        "recipe_file": RECIPE_FILE.exists(),
        "recipe_ingredient_file": RECIPE_INGREDIENT_FILE.exists(),
    }


def _clean_words(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonical_ingredient_name(raw: str) -> str:
    """Create a readable costing name without inventing quantities/conversions."""
    text = (raw or "").strip()
    low = _clean_words(text)

    exact = {
        "garlic crushed": "Crushed Garlic",
        "crushed garlic": "Crushed Garlic",
        "skim milk powder": "Skim Milk Powder",
        "diced lamb": "Diced Lamb",
        "diced beef": "Diced Beef",
        "diced chicken thigh": "Diced Chicken Thigh",
        "tomato paste": "Tomato Paste",
        "white wine": "White Wine",
        "lemon juice": "Lemon Juice",
        "cream": "Cream",
        "thickened cream": "Thickened Cream",
        "sour cream": "Sour Cream",
        "greek yoghurt": "Greek Yoghurt",
        "soy sauce": "Soy Sauce",
        "chicken stock": "Chicken Stock",
        "vegetable stock": "Vegetable Stock",
        "sweet potato": "Sweet Potato",
        "xanthan gum": "Xanthan Gum",
        "spinach leaves chopped": "Spinach Leaves",
        "bacon sliced": "Bacon",
        "cauliflower chopped": "Cauliflower",
        "potatoes": "Potatoes",
        "potatoes diced": "Potatoes",
        "potatoes peeled and chopped": "Potatoes",
        "carrots diced": "Carrots",
        "onions diced": "Onions",
        "leek diced": "Leek",
        "leeks diced": "Leeks",
        "leeks finely sliced": "Leeks",
        "zucchini diced": "Zucchini",
        "parsnip diced": "Parsnip",
        "parsnips diced": "Parsnips",
        "swede diced": "Swede",
        "green cabbage finely shredded": "Green Cabbage",
        "butter": "Butter",
        "honey": "Honey",
        "salt": "Salt",
    }
    if low in exact:
        return exact[low]

    # Remove preparation descriptors only for the costing label. The untouched
    # sponsor line remains in sponsor_recipe_ingredients for traceability.
    words = [
        w for w in re.split(r"\s+", re.sub(r"[,()]", " ", text).strip())
        if w.lower() not in {"diced", "chopped", "peeled", "rough", "finely", "fine", "sliced", "garnish"}
    ]
    cleaned = " ".join(words).strip()
    return cleaned.title() if cleaned else text


def import_supplier_file(path: Path = SUPPLIER_FILE) -> int:
    """Import Harbison's supplier comparison as reference analytics only.

    These quotes are never auto-applied to recipe costing and the app does not
    recommend a supplier. They remain useful for comparison/visualisation.
    """
    if not path.exists():
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f, connection() as c:
        for row in csv.DictReader(f):
            product = (row.get("product_name") or "").strip()
            if not product:
                continue
            c.execute(
                """INSERT INTO supplier_products(
                       category,product_name,pfd_price,superior_foods_price,sfd_price,
                       source_page,source_document,imported_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(product_name) DO UPDATE SET
                       category=excluded.category,
                       pfd_price=excluded.pfd_price,
                       superior_foods_price=excluded.superior_foods_price,
                       sfd_price=excluded.sfd_price,
                       source_page=excluded.source_page,
                       source_document=excluded.source_document,
                       imported_at=excluded.imported_at""",
                (
                    (row.get("category") or "").strip() or None,
                    product,
                    _float_or_none(row.get("pfd_price_aud")),
                    _float_or_none(row.get("superior_foods_price_aud")),
                    _float_or_none(row.get("sfd_price_aud")),
                    _int_or_none(row.get("source_page")),
                    (row.get("source_document") or "").strip() or None,
                    now,
                ),
            )
            count += 1
    return count


def _get_or_create_cost_ingredient(c, raw_name: str, unit: str):
    """Map only units that are already compatible with the costing engine.

    No cups/bunches/tins/kitchen-spoons are silently converted.
    """
    if unit not in SAFE_COST_UNITS:
        return None
    name = canonical_ingredient_name(raw_name)
    row = c.execute("SELECT id,base_unit FROM ingredients WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        if row[1] == unit:
            return row[0]
        # Same ingredient name but incompatible unit. Do not invent a conversion.
        variant = f"{name} [{unit}]"
        row2 = c.execute("SELECT id FROM ingredients WHERE lower(name)=lower(?)", (variant,)).fetchone()
        if row2:
            return row2[0]
        c.execute("INSERT INTO ingredients(name,base_unit,supplier,active) VALUES(?,?,NULL,1)", (variant, unit))
        return c.execute("SELECT id FROM ingredients WHERE name=?", (variant,)).fetchone()[0]

    c.execute("INSERT INTO ingredients(name,base_unit,supplier,active) VALUES(?,?,NULL,1)", (name, unit))
    return c.execute("SELECT id FROM ingredients WHERE name=?", (name,)).fetchone()[0]


def import_recipe_files(recipe_path: Path = RECIPE_FILE, ingredient_path: Path = RECIPE_INGREDIENT_FILE) -> tuple[int, int, int]:
    if not recipe_path.exists() or not ingredient_path.exists():
        return 0, 0, 0

    now = datetime.now().isoformat(timespec="seconds")
    recipe_count = 0
    line_count = 0
    mapped_count = 0

    with connection() as c:
        with recipe_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                recipe_name = (row.get("recipe_name") or "").strip()
                if not recipe_name:
                    continue

                category_name = (row.get("category") or "Recipe").strip() or "Recipe"
                c.execute("INSERT OR IGNORE INTO food_categories(name) VALUES(?)", (category_name,))
                category_id = c.execute("SELECT id FROM food_categories WHERE name=?", (category_name,)).fetchone()[0]
                c.execute(
                    """INSERT INTO food_items(name,category_id,manual_cost_per_kg,active)
                       VALUES(?,?,NULL,1)
                       ON CONFLICT(name) DO UPDATE SET category_id=excluded.category_id,active=1""",
                    (recipe_name, category_id),
                )
                food_item_id = c.execute("SELECT id FROM food_items WHERE name=?", (recipe_name,)).fetchone()[0]

                serves = int(float(row.get("serves") or 100))
                serving_size_g = float(row.get("serving_size_g") or 240)
                finished_yield_kg = serves * serving_size_g / 1000.0

                c.execute(
                    """INSERT INTO recipes(food_item_id,yield_kg,notes,active)
                       VALUES(?,?,?,1)
                       ON CONFLICT(food_item_id) DO UPDATE SET
                           yield_kg=excluded.yield_kg,
                           notes=excluded.notes,
                           active=1""",
                    (food_item_id, finished_yield_kg, "Harbison sponsor recipe. Raw recipe lines remain authoritative; costing uses only safely mapped kg/L/each lines."),
                )

                c.execute(
                    """INSERT INTO sponsor_recipes(
                           food_item_id,recipe_name,display_name,texture,serves,serving_size_g,
                           yield_loss_pct,allergens,dietary_notes,source_page,source_document,imported_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(recipe_name) DO UPDATE SET
                           food_item_id=excluded.food_item_id,
                           display_name=excluded.display_name,
                           texture=excluded.texture,
                           serves=excluded.serves,
                           serving_size_g=excluded.serving_size_g,
                           yield_loss_pct=excluded.yield_loss_pct,
                           allergens=excluded.allergens,
                           dietary_notes=excluded.dietary_notes,
                           source_page=excluded.source_page,
                           source_document=excluded.source_document,
                           imported_at=excluded.imported_at""",
                    (
                        food_item_id,
                        recipe_name,
                        (row.get("display_name") or recipe_name).strip(),
                        (row.get("texture") or "").strip() or None,
                        serves,
                        serving_size_g,
                        _float_or_none(row.get("yield_loss_pct")),
                        (row.get("allergens") or "").strip() or None,
                        (row.get("dietary_notes") or "").strip() or None,
                        _int_or_none(row.get("source_page")),
                        (row.get("source_document") or "").strip() or None,
                        now,
                    ),
                )
                recipe_count += 1

        recipe_ids = {
            r["recipe_name"]: r["id"]
            for r in [dict(x) for x in c.execute("SELECT id,recipe_name FROM sponsor_recipes").fetchall()]
        }
        with ingredient_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                recipe_name = (row.get("recipe_name") or "").strip()
                sponsor_rid = recipe_ids.get(recipe_name)
                if not sponsor_rid:
                    continue
                line_order = _int_or_none(row.get("line_order"))
                if line_order is None:
                    continue
                raw_name = (row.get("ingredient_name") or "").strip()
                qty = _float_or_none(row.get("quantity"))
                unit = (row.get("unit") or "").strip() or None

                c.execute(
                    """INSERT INTO sponsor_recipe_ingredients(
                           sponsor_recipe_id,line_order,quantity,unit,ingredient_name,source_document)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(sponsor_recipe_id,line_order) DO UPDATE SET
                           quantity=excluded.quantity,
                           unit=excluded.unit,
                           ingredient_name=excluded.ingredient_name,
                           source_document=excluded.source_document""",
                    (
                        sponsor_rid,
                        line_order,
                        qty,
                        unit,
                        raw_name,
                        (row.get("source_document") or "").strip() or None,
                    ),
                )
                line_count += 1

                # Safely map recipe costing only where the sponsor has already
                # provided a numeric kg/L/each quantity.
                if qty is not None and unit in SAFE_COST_UNITS:
                    ingredient_id = _get_or_create_cost_ingredient(c, raw_name, unit)
                    sponsor_recipe = c.execute("SELECT food_item_id FROM sponsor_recipes WHERE id=?", (sponsor_rid,)).fetchone()
                    recipe_row = c.execute("SELECT id FROM recipes WHERE food_item_id=?", (sponsor_recipe[0],)).fetchone()
                    if ingredient_id and recipe_row:
                        c.execute(
                            """INSERT INTO recipe_ingredients(recipe_id,ingredient_id,quantity,unit)
                               VALUES(?,?,?,?)
                               ON CONFLICT(recipe_id,ingredient_id) DO UPDATE SET
                                   quantity=excluded.quantity,unit=excluded.unit""",
                            (recipe_row[0], ingredient_id, qty, unit),
                        )
                        mapped_count += 1

    return recipe_count, line_count, mapped_count


def import_default_sponsor_files():
    """Reconcile Harbison reference files used by the prototype.

    Supplier data is retained for comparison charts only. Supplier recommendations
    and automatic supplier-to-recipe price application are intentionally excluded.
    """
    supplier_count = import_supplier_file()
    recipe_count, line_count, mapped_count = import_recipe_files()
    return {
        "supplier_rows": supplier_count,
        "recipes": recipe_count,
        "recipe_lines": line_count,
        "cost_mapped_lines": mapped_count,
    }


def ensure_sponsor_data_loaded():
    """Import/reconcile local sponsor reference files on app start.

    The import is idempotent and deliberately keeps sponsor data separate from
    operational waste transactions.
    """
    return import_default_sponsor_files()


def sponsor_ingredient_coverage():
    """Return counts used by the UI to show what is usable and what still needs confirmation."""
    total = fetchone("SELECT COUNT(*) n FROM sponsor_recipe_ingredients")["n"]
    safe = fetchone(
        "SELECT COUNT(*) n FROM sponsor_recipe_ingredients WHERE quantity IS NOT NULL AND unit IN ('kg','L','each')"
    )["n"]
    unique_raw = fetchone("SELECT COUNT(DISTINCT ingredient_name) n FROM sponsor_recipe_ingredients")["n"]
    mapped = fetchone(
        """SELECT COUNT(*) n FROM recipe_ingredients ri
           JOIN recipes r ON r.id=ri.recipe_id
           JOIN sponsor_recipes sr ON sr.food_item_id=r.food_item_id"""
    )["n"]
    priced = fetchone(
        """SELECT COUNT(DISTINCT ri.ingredient_id) n
           FROM recipe_ingredients ri
           JOIN recipes r ON r.id=ri.recipe_id
           JOIN sponsor_recipes sr ON sr.food_item_id=r.food_item_id
           JOIN ingredient_price_history ph ON ph.ingredient_id=ri.ingredient_id"""
    )["n"]
    return {
        "recipe_lines": total,
        "safe_cost_lines": safe,
        "unique_raw_ingredients": unique_raw,
        "mapped_cost_lines": mapped,
        "priced_cost_ingredients": priced,
    }


LEGACY_DEMO_FOODS = [
    "Porridge", "Corn Flakes", "Bread/Rolls/Toast", "Pancakes", "Scrambled Eggs", "Yoghurt",
    "Fruit Salad", "Vegetable Soup", "Chicken Casserole", "Beef Stew", "Fish Fillet",
    "Mashed Potato", "Rice", "Mixed Vegetables", "Carrots", "Apple Crumble", "Custard",
    "Tea/Coffee", "Juice",
]
LEGACY_DEMO_INGREDIENTS = [
    "Chicken breast", "Beef", "Fish", "Potato", "Rice", "Mixed vegetables", "Carrot", "Milk",
    "Egg", "Flour", "Sugar", "Stock/Sauce base",
]


def retire_legacy_demo_data():
    """Remove old prototype-only synthetic content while protecting sponsor and real records."""
    removed = {"demo_transactions": 0, "menu_rows": 0, "demo_food_items": 0, "demo_ingredients": 0, "placeholder_facilities": 0}
    with connection() as c:
        cur = c.execute("DELETE FROM transactions WHERE is_demo=1")
        removed["demo_transactions"] = cur.rowcount if cur.rowcount != -1 else 0

        # The original four-week menu was entirely seeded demo content.
        cur = c.execute("DELETE FROM menu_schedule")
        removed["menu_rows"] = cur.rowcount if cur.rowcount != -1 else 0

        protected_food_ids = {r[0] for r in c.execute("SELECT food_item_id FROM sponsor_recipes").fetchall()}
        protected_food_ids.update(r[0] for r in c.execute("SELECT DISTINCT food_item_id FROM harbison_menu_schedule").fetchall())
        for name in LEGACY_DEMO_FOODS:
            row = c.execute("SELECT id FROM food_items WHERE name=?", (name,)).fetchone()
            if not row or row[0] in protected_food_ids:
                continue
            real_tx = c.execute("SELECT 1 FROM transactions WHERE food_item_id=? AND is_demo=0 LIMIT 1", (row[0],)).fetchone()
            if real_tx:
                continue
            cur = c.execute("DELETE FROM food_items WHERE id=?", (row[0],))
            if cur.rowcount and cur.rowcount > 0:
                removed["demo_food_items"] += 1

        for name in LEGACY_DEMO_INGREDIENTS:
            row = c.execute("SELECT id FROM ingredients WHERE name=?", (name,)).fetchone()
            if not row:
                continue
            used = c.execute("SELECT 1 FROM recipe_ingredients WHERE ingredient_id=? LIMIT 1", (row[0],)).fetchone()
            if used:
                continue
            cur = c.execute("DELETE FROM ingredients WHERE id=?", (row[0],))
            if cur.rowcount and cur.rowcount > 0:
                removed["demo_ingredients"] += 1

        # Remove the two original placeholder facilities only when no real transaction
        # depends on them. The user can then enter the actual Harbison site names.
        for facility_name in ("Harbison Facility A", "Harbison Facility B"):
            row = c.execute("SELECT id FROM facilities WHERE name=?", (facility_name,)).fetchone()
            if not row:
                continue
            real_tx = c.execute("SELECT 1 FROM transactions WHERE facility_id=? AND is_demo=0 LIMIT 1", (row[0],)).fetchone()
            if real_tx:
                continue
            cur = c.execute("DELETE FROM facilities WHERE id=?", (row[0],))
            if cur.rowcount and cur.rowcount > 0:
                removed["placeholder_facilities"] += 1
    return removed
