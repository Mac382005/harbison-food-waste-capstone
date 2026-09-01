from datetime import date, datetime
import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, execute, setting, log_action
from src.menu import menu_items
from src.costing import food_cost_per_kg
from .common import money, fmt_pct


def pct(n,d):
    return None if d is None or d <= 0 else n/d*100


def page():
    user = require_roles("admin","manager","kitchen")
    page_header("KITCHEN OPERATIONS", "Record Food Waste", "Fast meal-by-meal entry with menu-aware food selection and automatic costing.")

    facilities = fetchall("SELECT * FROM facilities WHERE active=1 ORDER BY name")
    meals = fetchall("SELECT * FROM meals ORDER BY sort_order")

    with st.form("waste_entry", clear_on_submit=False):
        st.subheader("1 · Service context")
        c1,c2 = st.columns(2)
        facility_name = c1.selectbox("Facility", [f["name"] for f in facilities])
        fid = next(f["id"] for f in facilities if f["name"]==facility_name)
        areas = fetchall("SELECT * FROM service_areas WHERE facility_id=? AND active=1 ORDER BY name",(fid,))
        area_name = c2.selectbox("Service area", [a["name"] for a in areas])
        aid = next(a["id"] for a in areas if a["name"]==area_name)

        c3,c4 = st.columns(2)
        service_date = c3.date_input("Service date", date.today())
        meal_name = c4.selectbox("Meal service",[m["name"] for m in meals])
        mid = next(m["id"] for m in meals if m["name"]==meal_name)

        st.subheader("2 · Waste type and food")
        waste_type = st.radio("Waste type",["Production Waste","Plate Waste"],horizontal=True)
        items = menu_items(service_date, mid)
        if not items:
            items = fetchall("""SELECT fi.id,fi.name,fi.manual_cost_per_kg,fc.name category
                                FROM food_items fi LEFT JOIN food_categories fc ON fc.id=fi.category_id
                                WHERE fi.active=1 ORDER BY fc.name,fi.name""")
        labels = [f"{x['name']} · {x['category']}" for x in items]
        label = st.selectbox("Food item", labels)
        item = items[labels.index(label)]

        st.subheader("3 · Quantity")
        q1,q2,q3 = st.columns(3)
        prepared = q1.number_input("Prepared kg",min_value=0.0,value=0.0,step=.1,help="Needed for production-waste %. Leave 0 if unknown.")
        served = q2.number_input("Served kg",min_value=0.0,value=0.0,step=.1,help="Needed for plate-waste %. Leave 0 if unknown.")
        waste = q3.number_input("Waste kg",min_value=0.0,value=0.0,step=.1)

        residents = st.number_input("Residents / meals served (optional)",min_value=0,value=0,step=1)
        reasons = ["Overproduction","Preparation/trimming waste","Quality issue","Expired / out of date","Spoiled","Mishandled","Temperature/time issue","Other"] if waste_type=="Production Waste" else ["Presented but not consumed","Quality issue","Temperature/time issue","Other"]
        reason = st.selectbox("Waste reason (optional)",["Not specified"]+reasons)
        notes = st.text_area("Notes (optional)",max_chars=300)

        prep = prepared if prepared > 0 else None
        srv = served if served > 0 else None
        wp = pct(waste, prep if waste_type=="Production Waste" else srv)
        cost, cost_source = food_cost_per_kg(item["id"], service_date)
        waste_cost = waste*cost if cost is not None else None
        kpi = float(setting("plate_waste_kpi","20") or 20)

        st.subheader("4 · Review")
        r1,r2,r3,r4 = st.columns(4)
        r1.metric("Waste",f"{waste:.2f} kg")
        r2.metric("Waste %",fmt_pct(wp))
        r3.metric("Estimated cost",money(waste_cost))
        r4.metric("Current cost/kg",money(cost),help=cost_source)

        errors = []
        if waste_type=="Production Waste" and prep is not None and waste>prep:
            errors.append("Production waste cannot exceed prepared weight.")
        if waste_type=="Plate Waste" and srv is not None and waste>srv:
            errors.append("Plate waste cannot exceed served weight.")
        for e in errors:
            st.error(e)
        if waste_type=="Plate Waste" and wp is not None and wp > kpi:
            st.warning(f"Plate waste is above the configured {kpi:.1f}% KPI.")

        submitted = st.form_submit_button("Save waste record",type="primary",use_container_width=True,disabled=(waste<=0 or bool(errors)))

    if submitted:
        execute(
            """INSERT INTO transactions(
            created_at,service_date,facility_id,service_area_id,meal_id,food_item_id,waste_type,
            prepared_kg,served_kg,waste_kg,waste_percentage,cost_per_kg_snapshot,waste_cost,
            waste_reason,resident_count,notes,recorded_by,is_demo)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (datetime.now().isoformat(timespec="seconds"),service_date.isoformat(),fid,aid,mid,item["id"],waste_type,
             prep,srv,waste,wp,cost,waste_cost,None if reason=="Not specified" else reason,residents or None,notes.strip() or None,user["id"]),
        )
        log_action(user["id"],"CREATE_WASTE_RECORD",f"{waste_type}: {item['name']} {waste:.2f}kg at {facility_name}/{area_name}")
        st.success("Waste record saved.")
