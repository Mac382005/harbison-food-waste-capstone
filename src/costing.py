from __future__ import annotations

from datetime import date
from .db import fetchone, fetchall


def ingredient_unit_cost(ingredient_id: int, as_of: date | str | None = None):
    if as_of is None:
        as_of = date.today().isoformat()
    elif isinstance(as_of, date):
        as_of = as_of.isoformat()
    return fetchone(
        """SELECT unit_cost,effective_date,purchase_price,pack_quantity,pack_unit
           FROM ingredient_price_history
           WHERE ingredient_id=? AND effective_date<=?
           ORDER BY effective_date DESC,id DESC LIMIT 1""",
        (ingredient_id, as_of),
    )


def recipe_cost_status(food_item_id: int, as_of: date | str | None = None):
    recipe = fetchone("SELECT * FROM recipes WHERE food_item_id=? AND active=1", (food_item_id,))
    if not recipe:
        return {"recipe": None, "mapped": 0, "priced": 0, "unpriced": [], "detail": [], "complete": False}

    rows = fetchall(
        """SELECT ri.quantity,ri.unit,i.id ingredient_id,i.name ingredient,i.base_unit
           FROM recipe_ingredients ri
           JOIN ingredients i ON i.id=ri.ingredient_id
           WHERE ri.recipe_id=? AND i.active=1
           ORDER BY i.name""",
        (recipe["id"],),
    )
    detail = []
    unpriced = []
    for row in rows:
        price = ingredient_unit_cost(row["ingredient_id"], as_of)
        if price:
            line_cost = row["quantity"] * price["unit_cost"]
            detail.append({**row, "unit_cost": price["unit_cost"], "line_cost": line_cost, "priced": True})
        else:
            unpriced.append(row["ingredient"])
            detail.append({**row, "unit_cost": None, "line_cost": None, "priced": False})
    return {
        "recipe": recipe,
        "mapped": len(rows),
        "priced": len(rows) - len(unpriced),
        "unpriced": unpriced,
        "detail": detail,
        "complete": bool(rows) and not unpriced,
    }


def recipe_cost(food_item_id: int, as_of: date | str | None = None):
    status = recipe_cost_status(food_item_id, as_of)
    recipe = status["recipe"]
    if not recipe or not status["complete"]:
        return None

    total = sum(row["line_cost"] for row in status["detail"] if row["line_cost"] is not None)
    return {
        "recipe_id": recipe["id"],
        "yield_kg": recipe["yield_kg"],
        "total_cost": total,
        "cost_per_kg": total / recipe["yield_kg"] if recipe["yield_kg"] else None,
        "detail": status["detail"],
    }


def food_cost_per_kg(food_item_id: int, as_of: date | str | None = None):
    rc = recipe_cost(food_item_id, as_of)
    if rc and rc["cost_per_kg"] is not None:
        return rc["cost_per_kg"], "Harbison recipe-derived"

    link = fetchone("SELECT recipe_food_item_id FROM menu_item_recipe_links WHERE menu_food_item_id=?", (food_item_id,))
    if link:
        rc = recipe_cost(link["recipe_food_item_id"], as_of)
        if rc and rc["cost_per_kg"] is not None:
            return rc["cost_per_kg"], "Linked Harbison recipe-derived"

    item = fetchone("SELECT manual_cost_per_kg FROM food_items WHERE id=?", (food_item_id,))
    fallback = item["manual_cost_per_kg"] if item else None
    return fallback, "Manual fallback" if fallback is not None else "Cost not yet available"
