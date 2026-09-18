import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.db import fetchall, fetchone, execute, log_action
from src.costing import recipe_cost, recipe_cost_status


def page():
    user = require_roles("admin", "manager")
    page_header(
        "COST MANAGEMENT",
        "Recipes & Costing",
        "Harbison sponsor recipes are the primary recipe source. Costing is only completed where ingredient units and prices are confirmed.",
    )

    sponsor_only = st.toggle("Show Harbison sponsor recipes only", value=True)
    if sponsor_only:
        foods = fetchall(
            """SELECT fi.id,fi.name,fi.manual_cost_per_kg
               FROM food_items fi JOIN sponsor_recipes sr ON sr.food_item_id=fi.id
               WHERE fi.active=1 ORDER BY fi.name"""
        )
    else:
        foods = fetchall("SELECT id,name,manual_cost_per_kg FROM food_items WHERE active=1 ORDER BY name")

    if not foods:
        st.info("No recipes are available yet. Import sponsor recipe files from Sponsor Data.")
        return

    name = st.selectbox("Food item", [f["name"] for f in foods])
    food = next(f for f in foods if f["name"] == name)
    recipe = fetchone("SELECT * FROM recipes WHERE food_item_id=?", (food["id"],))
    sponsor = fetchone("SELECT * FROM sponsor_recipes WHERE food_item_id=?", (food["id"],))

    if sponsor:
        render_source_badges(
            [
                ("Harbison sponsor recipe", "source-green"),
                ("Reference recipe from sponsor files", "source-blue"),
            ]
        )
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Standard serves", int(sponsor["serves"]))
        s2.metric("Serving size", f"{sponsor['serving_size_g']:.0f} g")
        s3.metric("Texture", sponsor["texture"] or "N/A")
        s4.metric(
            "Listed yield loss",
            "N/A" if sponsor["yield_loss_pct"] is None else f"{sponsor['yield_loss_pct']:.0f}%",
        )
        st.write(f"**Allergens:** {sponsor['allergens'] or 'None listed'}")
        if sponsor["dietary_notes"]:
            st.info(sponsor["dietary_notes"])
        st.caption(f"Source: {sponsor['source_document'] or 'Sponsor file'}, page {sponsor['source_page'] or '?'}")

        raw_lines = fetchall(
            """SELECT ingredient_name,quantity,unit
               FROM sponsor_recipe_ingredients
               WHERE sponsor_recipe_id=? ORDER BY line_order""",
            (sponsor["id"],),
        )
        if raw_lines:
            with st.expander("Sponsor recipe ingredient reference", expanded=True):
                rdf = pd.DataFrame(raw_lines).rename(
                    columns={"ingredient_name": "Ingredient", "quantity": "Quantity", "unit": "Unit"}
                )
                st.dataframe(rdf, use_container_width=True, hide_index=True)
                st.caption(
                    "These are the sponsor-provided recipe lines. Units such as cups, tins, bunches or kitchen spoons remain unchanged until Harbison confirms a conversion."
                )
    else:
        render_source_badges(
            [
                ("Manual/non-sponsor recipe", "source-purple"),
                ("Not part of current sponsor recipe files", "source-orange"),
            ]
        )

    if not recipe:
        st.warning("No costing recipe exists for this food item yet.")
        if not sponsor:
            yield_kg = st.number_input("Create recipe yield (kg)", min_value=.1, value=10.0, step=.5)
            if st.button("Create manual recipe"):
                execute(
                    "INSERT INTO recipes(food_item_id,yield_kg,notes) VALUES(?,?,?)",
                    (food["id"], yield_kg, "Manual recipe"),
                )
                log_action(user["id"], "CREATE_RECIPE", name)
                st.success("Recipe created. Reload this page to add ingredients.")
        return

    c1, c2 = st.columns([3, 1])
    new_yield = c1.number_input(
        "Recipe finished yield (kg)", min_value=.1, value=float(recipe["yield_kg"]), step=.5
    )
    if c2.button("Update yield", use_container_width=True):
        execute("UPDATE recipes SET yield_kg=? WHERE id=?", (new_yield, recipe["id"]))
        log_action(user["id"], "UPDATE_RECIPE_YIELD", f"{name}: {new_yield}kg")
        st.success("Yield updated.")

    status = recipe_cost_status(food["id"])
    st.subheader("Current costing")
    c1, c2, c3 = st.columns(3)
    c1.metric("Mapped cost ingredients", status["mapped"])
    c2.metric("Mapped ingredients with prices", status["priced"])
    coverage = (status["priced"] / status["mapped"] * 100) if status["mapped"] else 0
    c3.metric("Mapped-price coverage", f"{coverage:.0f}%")

    rc = recipe_cost(food["id"])
    if rc:
        a, b, c = st.columns(3)
        a.metric("Recipe batch cost", f"A${rc['total_cost']:,.2f}")
        b.metric("Finished yield", f"{rc['yield_kg']:.2f} kg")
        c.metric("Derived cost/kg", f"A${rc['cost_per_kg']:,.2f}")
    else:
        if status["mapped"] == 0:
            st.info("No costable kg/L/each ingredients have been mapped yet for this recipe.")
        elif status["unpriced"]:
            st.info(
                "Costing is not complete yet. Ingredient prices are still needed for: "
                + ", ".join(status["unpriced"][:8])
                + ("…" if len(status["unpriced"]) > 8 else "")
            )

    if status["detail"]:
        detail = pd.DataFrame(status["detail"])
        detail = detail[["ingredient", "quantity", "unit", "unit_cost", "line_cost", "priced"]]
        detail = detail.rename(
            columns={
                "ingredient": "Ingredient",
                "quantity": "Quantity",
                "unit": "Unit",
                "unit_cost": "Unit cost",
                "line_cost": "Line cost",
                "priced": "Priced",
            }
        )
        st.dataframe(detail, use_container_width=True, hide_index=True)

    st.subheader("Cost ingredients")
    st.caption(
        "Sponsor import automatically maps only numeric kg/L/each lines. Use this section for confirmed additions or corrections; do not invent conversions for cups, tins, bunches or unspecified quantities."
    )
    ingredients = fetchall("SELECT * FROM ingredients WHERE active=1 ORDER BY name")
    if not ingredients:
        st.info("No cost ingredients available yet.")
        return

    with st.form("add_ing"):
        ing_name = st.selectbox("Add/update cost ingredient", [i["name"] for i in ingredients])
        ing = next(i for i in ingredients if i["name"] == ing_name)
        qty = st.number_input(f"Quantity ({ing['base_unit']})", min_value=0.0, value=1.0, step=.1)
        save = st.form_submit_button("Add / update recipe ingredient")
    if save:
        execute(
            """INSERT INTO recipe_ingredients(recipe_id,ingredient_id,quantity,unit)
               VALUES(?,?,?,?)
               ON CONFLICT(recipe_id,ingredient_id) DO UPDATE SET quantity=excluded.quantity,unit=excluded.unit""",
            (recipe["id"], ing["id"], qty, ing["base_unit"]),
        )
        log_action(user["id"], "UPDATE_RECIPE_INGREDIENT", f"{name}: {ing_name} {qty}{ing['base_unit']}")
        st.success("Recipe ingredient saved.")
