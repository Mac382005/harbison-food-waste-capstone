from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, fetchone, execute, log_action
from src.costing import ingredient_unit_cost
from src.sponsor_import import canonical_ingredient_name, sponsor_ingredient_coverage


def _ingredient_table():
    ingredients = fetchall("SELECT * FROM ingredients WHERE active=1 ORDER BY name")
    sponsor_used_ids = {
        r["ingredient_id"]
        for r in fetchall(
            """SELECT DISTINCT ri.ingredient_id
               FROM recipe_ingredients ri
               JOIN recipes r ON r.id=ri.recipe_id
               JOIN sponsor_recipes sr ON sr.food_item_id=r.food_item_id"""
        )
    }

    rows = []
    for ing in ingredients:
        price = ingredient_unit_cost(ing["id"])
        source = "Harbison recipe" if ing["id"] in sponsor_used_ids else "Manual/general"
        rows.append(
            {
                "Ingredient": ing["name"],
                "Source": source,
                "Unit": ing["base_unit"],
                "Price status": "Added" if price else "Needed",
                "Current unit cost": None if not price else price["unit_cost"],
                "Effective date": None if not price else price["effective_date"],
            }
        )
    return pd.DataFrame(rows)


def _coverage_table():
    rows = fetchall(
        """SELECT sri.ingredient_name,sri.unit,COUNT(DISTINCT sr.id) recipe_count,COUNT(*) line_count
           FROM sponsor_recipe_ingredients sri
           JOIN sponsor_recipes sr ON sr.id=sri.sponsor_recipe_id
           GROUP BY sri.ingredient_name,sri.unit
           ORDER BY sri.ingredient_name,sri.unit"""
    )
    out = []
    for r in rows:
        unit = r["unit"] or "Unspecified"
        cname = canonical_ingredient_name(r["ingredient_name"])
        mapped = None
        if unit in {"kg", "L", "each"}:
            mapped = fetchone(
                "SELECT id,name FROM ingredients WHERE lower(name)=lower(?) AND base_unit=?",
                (cname, unit),
            ) or fetchone(
                "SELECT id,name FROM ingredients WHERE lower(name)=lower(?) AND base_unit=?",
                (f"{cname} [{unit}]", unit),
            )
        price = ingredient_unit_cost(mapped["id"]) if mapped else None
        out.append(
            {
                "Harbison ingredient": r["ingredient_name"],
                "Unit": unit,
                "Recipes": r["recipe_count"],
                "Mapping": mapped["name"] if mapped else "Needs confirmation",
                "Price status": "Added" if price else ("Needed" if mapped else "Not mapped"),
            }
        )
    return pd.DataFrame(out)


def page():
    user = require_roles("admin", "manager")
    page_header(
        "COST MANAGEMENT",
        "Ingredients & Prices",
        "Use Harbison recipe ingredients where units are reliable, then enter confirmed ingredient prices manually.",
    )
    st.caption(
        "Status is shown as plain text rather than row colours: Harbison recipe / Manual-general, plus Mapping and Price status."
    )

    coverage = sponsor_ingredient_coverage()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recipe lines", coverage["recipe_lines"])
    c2.metric("Safe kg/L/each", coverage["safe_cost_lines"])
    c3.metric("Mapped lines", coverage["mapped_cost_lines"])
    c4.metric("Priced mapped", coverage["priced_cost_ingredients"])

    tab1, tab2 = st.tabs(["Harbison ingredient coverage", "Ingredient prices"])

    with tab1:
        st.caption(
            "Only kg, L and each are auto-mapped. Cups, tins, bunches, spoons and unspecified quantities stay unconverted until Harbison confirms them."
        )
        df = _coverage_table()
        if df.empty:
            st.info("No Harbison recipe ingredient data is loaded yet.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        df = _ingredient_table()
        if not df.empty:
            display = df.copy()
            display["Current unit cost"] = display["Current unit cost"].apply(
                lambda x: "" if pd.isna(x) else f"A${x:,.3f}"
            )
            st.dataframe(display, use_container_width=True, hide_index=True)

        with st.expander("Add a manual cost ingredient"):
            with st.form("new_ing"):
                a, b = st.columns(2)
                name = a.text_input("Ingredient name")
                unit = b.selectbox("Base unit", ["kg", "L", "each"])
                save = st.form_submit_button("Add ingredient")
            if save and name.strip():
                execute(
                    "INSERT OR IGNORE INTO ingredients(name,base_unit,supplier,active) VALUES(?,?,NULL,1)",
                    (name.strip(), unit),
                )
                log_action(user["id"], "CREATE_INGREDIENT", name.strip())
                st.rerun()

        ingredients = fetchall("SELECT * FROM ingredients WHERE active=1 ORDER BY name")
        if ingredients:
            st.subheader("Record ingredient price")
            with st.form("price"):
                n = st.selectbox("Ingredient", [i["name"] for i in ingredients])
                ing = next(i for i in ingredients if i["name"] == n)
                a, b, c = st.columns(3)
                eff = a.date_input("Effective date", date.today())
                qty = b.number_input(
                    f"Pack quantity ({ing['base_unit']})", min_value=.001, value=1.0, step=.1
                )
                purchase = c.number_input("Purchase price (AUD)", min_value=0.0, value=0.0, step=1.0)
                unit_cost = purchase / qty
                st.metric(f"Cost per {ing['base_unit']}", f"A${unit_cost:,.3f}")
                submit = st.form_submit_button("Save price", type="primary")
            if submit:
                execute(
                    """INSERT INTO ingredient_price_history(
                           ingredient_id,effective_date,pack_quantity,pack_unit,purchase_price,
                           unit_cost,recorded_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        ing["id"], eff.isoformat(), qty, ing["base_unit"], purchase, unit_cost,
                        user["id"], datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                log_action(user["id"], "UPDATE_INGREDIENT_PRICE", n)
                st.success("Price saved.")
