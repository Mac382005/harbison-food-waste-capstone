from datetime import date
import pandas as pd
import streamlit as st
from src.auth import require_roles
from src.styles import page_header
from src.db import fetchall, fetchone, execute, log_action


def page():
    user=require_roles("admin","manager")
    page_header("CONFIGURATION","Menu & Locations","Manage real Harbison locations and review the imported Autumn/Winter four-week menu.")
    tab1,tab2,tab3=st.tabs(["Locations","Four-week menu","Food items"])
    with tab1:
        facilities=fetchall("SELECT * FROM facilities WHERE active=1 ORDER BY name")
        st.subheader("Facilities")
        if facilities: st.dataframe(pd.DataFrame(facilities),use_container_width=True,hide_index=True)
        else: st.info("Add the real Harbison facility names below.")
        with st.expander("Add / rename facility"):
            new=st.text_input("New facility name")
            if st.button("Add facility",disabled=not new.strip()): execute("INSERT OR IGNORE INTO facilities(name,active) VALUES(?,1)",(new.strip(),)); log_action(user["id"],"ADD_FACILITY",new.strip()); st.rerun()
        facilities=fetchall("SELECT * FROM facilities WHERE active=1 ORDER BY name")
        if facilities:
            fac=st.selectbox("Facility",[f["name"] for f in facilities]); fid=next(f["id"] for f in facilities if f["name"]==fac); areas=fetchall("SELECT id,name FROM service_areas WHERE facility_id=? AND active=1 ORDER BY name",(fid,)); st.subheader("Dining / service areas")
            if areas: st.dataframe(pd.DataFrame(areas),use_container_width=True,hide_index=True)
            area=st.text_input("Add service area")
            if st.button("Add service area",disabled=not area.strip()): execute("INSERT OR IGNORE INTO service_areas(facility_id,name,active) VALUES(?,?,1)",(fid,area.strip())); log_action(user["id"],"ADD_SERVICE_AREA",area.strip()); st.rerun()
    with tab2:
        menu=fetchone("SELECT * FROM menu_settings WHERE id=1"); start=st.date_input("Week 1 cycle start date",date.fromisoformat(menu["cycle_start_date"])); st.caption("Confirm this date with Alice. It controls which menu week is shown for each service date.")
        if st.button("Save cycle start date"): execute("UPDATE menu_settings SET cycle_start_date=? WHERE id=1",(start.isoformat(),)); log_action(user["id"],"UPDATE_MENU_START",start.isoformat()); st.success("Saved.")
        variants=[r["menu_variant"] for r in fetchall("SELECT DISTINCT menu_variant FROM harbison_menu_schedule ORDER BY menu_variant")]; a,b,c=st.columns(3); variant=a.selectbox("Menu type",variants); week=b.selectbox("Week",[1,2,3,4]); day=c.selectbox("Day",["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
        rows=fetchall("""SELECT meal_service AS Meal,component AS Component,menu_label AS Item,category AS Category,linked_recipe_name AS Recipe
                         FROM harbison_menu_schedule WHERE menu_variant=? AND week_number=? AND day_name=? ORDER BY CASE meal_service WHEN 'Breakfast' THEN 1 WHEN 'Morning Tea' THEN 2 WHEN 'Lunch' THEN 3 WHEN 'Afternoon Tea' THEN 4 WHEN 'Dinner' THEN 5 ELSE 9 END,component,menu_label""",(variant,week,day))
        st.metric("Scheduled items",len(rows)); st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with tab3:
        foods=fetchall("""SELECT fi.name,fc.name category,CASE WHEN sr.id IS NOT NULL THEN 'Validated Harbison recipe' WHEN EXISTS(SELECT 1 FROM harbison_menu_schedule h WHERE h.food_item_id=fi.id) THEN 'Harbison menu item' ELSE 'Manual' END source
                          FROM food_items fi LEFT JOIN food_categories fc ON fc.id=fi.category_id LEFT JOIN sponsor_recipes sr ON sr.food_item_id=fi.id WHERE fi.active=1 ORDER BY source,category,fi.name""")
        st.dataframe(pd.DataFrame(foods),use_container_width=True,hide_index=True)
