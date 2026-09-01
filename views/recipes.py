import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, fetchone, execute, log_action
from src.costing import recipe_cost


def page():
    user=require_roles("admin","manager")
    page_header("COST MANAGEMENT", "Recipes & Costing", "Recipe yields connect raw-material prices to an estimated finished-food cost per kilogram.")

    foods=fetchall("SELECT id,name,manual_cost_per_kg FROM food_items WHERE active=1 ORDER BY name")
    name=st.selectbox("Food item",[f["name"] for f in foods])
    food=next(f for f in foods if f["name"]==name)
    recipe=fetchone("SELECT * FROM recipes WHERE food_item_id=?",(food["id"],))

    if not recipe:
        st.info(f"No ingredient-level recipe exists for {name}. The system will use the manual fallback cost of A${food['manual_cost_per_kg'] or 0:.2f}/kg.")
        if user["role"] in {"admin","manager"}:
            yield_kg=st.number_input("Create recipe yield (kg)",min_value=.1,value=10.0,step=.5)
            if st.button("Create recipe"):
                execute("INSERT INTO recipes(food_item_id,yield_kg,notes) VALUES(?,?,?)",(food["id"],yield_kg,"Created in prototype"))
                log_action(user["id"],"CREATE_RECIPE",name)
                st.success("Recipe created. Reload this page to add ingredients.")
        return

    c1,c2=st.columns(2)
    new_yield=c1.number_input("Recipe finished yield (kg)",min_value=.1,value=float(recipe["yield_kg"]),step=.5)
    if c2.button("Update yield"):
        execute("UPDATE recipes SET yield_kg=? WHERE id=?",(new_yield,recipe["id"]))
        log_action(user["id"],"UPDATE_RECIPE_YIELD",f"{name}: {new_yield}kg")
        st.success("Yield updated.")

    rc=recipe_cost(food["id"])
    if rc:
        a,b,c=st.columns(3)
        a.metric("Recipe batch cost",f"A${rc['total_cost']:,.2f}")
        b.metric("Finished yield",f"{rc['yield_kg']:.2f} kg")
        c.metric("Derived cost/kg",f"A${rc['cost_per_kg']:,.2f}")

        detail_rows = rc.get("detail") or []
        if detail_rows:
            detail = pd.DataFrame(detail_rows)
            wanted = ["ingredient","quantity","unit","unit_cost","line_cost"]
            # Reindex is safe even if one optional column is unexpectedly absent.
            detail = detail.reindex(columns=wanted)
            st.dataframe(detail,use_container_width=True,hide_index=True)
        else:
            st.info("This recipe does not have any ingredients yet. Add at least one ingredient below to calculate recipe cost.")
    else:
        st.info(
            "This recipe exists but has no complete ingredient-level costing yet. "
            "Until ingredients and prices are available, new waste records will use the food item's manual fallback cost."
        )

    ingredients=fetchall("SELECT * FROM ingredients WHERE active=1 ORDER BY name")
    with st.form("add_ing"):
        ing_name=st.selectbox("Add/update ingredient",[i["name"] for i in ingredients])
        ing=next(i for i in ingredients if i["name"]==ing_name)
        qty=st.number_input(f"Quantity ({ing['base_unit']})",min_value=0.0,value=1.0,step=.1)
        save=st.form_submit_button("Add / update recipe ingredient")
    if save:
        execute(
            """INSERT INTO recipe_ingredients(recipe_id,ingredient_id,quantity,unit)
               VALUES(?,?,?,?)
               ON CONFLICT(recipe_id,ingredient_id) DO UPDATE SET quantity=excluded.quantity,unit=excluded.unit""",
            (recipe["id"],ing["id"],qty,ing["base_unit"]),
        )
        log_action(user["id"],"UPDATE_RECIPE_INGREDIENT",f"{name}: {ing_name} {qty}{ing['base_unit']}")
        st.success("Recipe ingredient saved.")
