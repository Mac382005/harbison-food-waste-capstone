from __future__ import annotations

from datetime import date
from .db import fetchone, fetchall


def ingredient_unit_cost(ingredient_id: int, as_of: date | str | None = None):
    if as_of is None:
        as_of = date.today().isoformat()
    elif isinstance(as_of, date):
        as_of = as_of.isoformat()
    r = fetchone(
        """SELECT unit_cost,effective_date,purchase_price,pack_quantity,pack_unit
           FROM ingredient_price_history
           WHERE ingredient_id=? AND effective_date<=?
           ORDER BY effective_date DESC,id DESC LIMIT 1""",
        (ingredient_id, as_of),
    )
    return r


def recipe_cost(food_item_id: int, as_of: date | str | None = None):
    recipe = fetchone("SELECT * FROM recipes WHERE food_item_id=? AND active=1", (food_item_id,))
    if not recipe:
        return None
    rows = fetchall(
        """SELECT ri.quantity,ri.unit,i.id ingredient_id,i.name ingredient,i.base_unit
           FROM recipe_ingredients ri
           JOIN ingredients i ON i.id=ri.ingredient_id
           WHERE ri.recipe_id=? AND i.active=1""",
        (recipe["id"],),
    )

    # A recipe shell may exist before any ingredients have been added.
    # Treat that as "no recipe costing available yet" so callers can
    # safely fall back to the manual food-item cost instead of returning
    # a misleading A$0.00/kg recipe cost.
    if not rows:
        return None

    total = 0.0
    detail = []
    for r in rows:
        price = ingredient_unit_cost(r["ingredient_id"], as_of)
        if not price:
            return None
        cost = r["quantity"] * price["unit_cost"]
        total += cost
        detail.append({**r, "unit_cost": price["unit_cost"], "line_cost": cost})
    return {
        "recipe_id": recipe["id"],
        "yield_kg": recipe["yield_kg"],
        "total_cost": total,
        "cost_per_kg": total / recipe["yield_kg"] if recipe["yield_kg"] else None,
        "detail": detail,
    }


def food_cost_per_kg(food_item_id: int, as_of: date | str | None = None):
    rc = recipe_cost(food_item_id, as_of)
    if rc and rc["cost_per_kg"] is not None:
        return rc["cost_per_kg"], "Recipe-derived"
    item = fetchone("SELECT manual_cost_per_kg FROM food_items WHERE id=?", (food_item_id,))
    return (item["manual_cost_per_kg"] if item else None), "Manual fallback"
