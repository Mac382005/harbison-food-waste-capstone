from datetime import date
import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, fetchone, execute, set_setting, setting, log_action


def page():
    user=require_roles("admin","manager")
    page_header("CONFIGURATION", "Menu & Locations", "Slow-changing reference data: facilities, dining areas, meal services and the four-week menu cycle.")

    tab1,tab2,tab3=st.tabs(["Locations","Menu cycle","Food items"])

    with tab1:
        st.dataframe(fetchall("SELECT * FROM facilities ORDER BY name"),use_container_width=True,hide_index=True)
        facilities=fetchall("SELECT * FROM facilities WHERE active=1 ORDER BY name")
        fac=st.selectbox("Facility",[f["name"] for f in facilities])
        fid=next(f["id"] for f in facilities if f["name"]==fac)
        st.dataframe(fetchall("SELECT id,name,active FROM service_areas WHERE facility_id=? ORDER BY name",(fid,)),use_container_width=True,hide_index=True)
        if user["role"]=="admin":
            new_area=st.text_input("Add service area")
            if st.button("Add service area",disabled=not new_area.strip()):
                execute("INSERT OR IGNORE INTO service_areas(facility_id,name) VALUES(?,?)",(fid,new_area.strip()))
                log_action(user["id"],"ADD_SERVICE_AREA",f"{fac}: {new_area.strip()}")
                st.success("Service area added.")

    with tab2:
        menu=fetchone("SELECT * FROM menu_settings WHERE id=1")
        start=st.date_input("Cycle start date",date.fromisoformat(menu["cycle_start_date"]))
        if st.button("Save cycle start date"):
            execute("UPDATE menu_settings SET cycle_start_date=? WHERE id=1",(start.isoformat(),))
            log_action(user["id"],"UPDATE_MENU_START",start.isoformat())
            st.success("Menu cycle start updated.")
        st.caption("The prototype uses a four-week rotation. A full drag-and-drop menu editor can be added later.")
        schedule=fetchall(
            """SELECT ms.week_number,ms.day_of_week,m.name meal,fi.name food_item
               FROM menu_schedule ms JOIN meals m ON m.id=ms.meal_id JOIN food_items fi ON fi.id=ms.food_item_id
               ORDER BY ms.week_number,ms.day_of_week,m.sort_order,fi.name"""
        )
        st.dataframe(pd.DataFrame(schedule).head(300),use_container_width=True,hide_index=True)

    with tab3:
        foods=fetchall(
            """SELECT fi.id,fi.name,fc.name category,fi.manual_cost_per_kg
               FROM food_items fi LEFT JOIN food_categories fc ON fc.id=fi.category_id ORDER BY fc.name,fi.name"""
        )
        st.dataframe(foods,use_container_width=True,hide_index=True)
