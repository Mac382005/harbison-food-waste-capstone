from datetime import date, datetime
import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, fetchone, execute, log_action
from src.costing import ingredient_unit_cost


def page():
    user=require_roles("admin","manager")
    page_header("COST MANAGEMENT", "Ingredients & Prices", "Update raw-material prices without rewriting historical waste costs.")

    ingredients=fetchall("SELECT * FROM ingredients WHERE active=1 ORDER BY name")
    rows=[]
    for i in ingredients:
        p=ingredient_unit_cost(i["id"])
        rows.append({
            "Ingredient":i["name"],"Supplier":i["supplier"],"Unit":i["base_unit"],
            "Current unit cost":None if not p else p["unit_cost"],
            "Effective date":None if not p else p["effective_date"],
        })
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    st.subheader("Record a new supplier price")
    with st.form("price_update"):
        name=st.selectbox("Ingredient",[i["name"] for i in ingredients])
        ing=next(i for i in ingredients if i["name"]==name)
        c1,c2,c3=st.columns(3)
        effective=c1.date_input("Effective date",date.today())
        pack_qty=c2.number_input(f"Pack quantity ({ing['base_unit']})",min_value=.001,value=10.0,step=.5)
        purchase=c3.number_input("Purchase price (AUD)",min_value=0.0,value=50.0,step=1.0)
        unit_cost=purchase/pack_qty if pack_qty else 0
        st.metric(f"Calculated cost per {ing['base_unit']}",f"A${unit_cost:,.3f}")
        submit=st.form_submit_button("Save new price",type="primary",use_container_width=True)

    if submit:
        execute(
            """INSERT INTO ingredient_price_history(
            ingredient_id,effective_date,pack_quantity,pack_unit,purchase_price,unit_cost,recorded_by,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (ing["id"],effective.isoformat(),pack_qty,ing["base_unit"],purchase,unit_cost,user["id"],datetime.now().isoformat(timespec="seconds")),
        )
        log_action(user["id"],"UPDATE_INGREDIENT_PRICE",f"{name}: A${purchase:.2f}/{pack_qty:g}{ing['base_unit']}")
        st.success("New ingredient price saved. New waste transactions and recipe costing will use the effective price; old transactions keep their stored cost snapshot.")

    st.subheader("Price history")
    selected=st.selectbox("Ingredient history",[i["name"] for i in ingredients],key="history_ing")
    iid=next(i["id"] for i in ingredients if i["name"]==selected)
    hist=fetchall(
        """SELECT p.effective_date,p.pack_quantity,p.pack_unit,p.purchase_price,p.unit_cost,
                  COALESCE(u.display_name,'System') recorded_by
           FROM ingredient_price_history p LEFT JOIN users u ON u.id=p.recorded_by
           WHERE p.ingredient_id=? ORDER BY p.effective_date DESC,p.id DESC""",(iid,))
    st.dataframe(hist,use_container_width=True,hide_index=True)
