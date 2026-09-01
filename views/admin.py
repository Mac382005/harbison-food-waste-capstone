import streamlit as st

from src.auth import require_roles
from src.styles import page_header
from src.db import fetchone, execute, setting, set_setting, fetchall, log_action
from src.demo import generate_demo_data


def page():
    user=require_roles("admin")
    page_header("SYSTEM", "Prototype Administration", "Synthetic data, KPI configuration, database counts and audit events.")

    tab1,tab2,tab3=st.tabs(["Synthetic data","KPI & system","Audit log"])

    with tab1:
        n=fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=1")["n"]
        st.metric("Synthetic transactions stored",n)
        st.caption("V2 generates exactly 90 days across every active facility, service area and all six meal services. With the seeded 8 service areas, this is about 8,640 transactions.")
        if st.button("Generate 90-day synthetic dataset",type="primary"):
            made=generate_demo_data(90)
            st.success(f"Generated {made} synthetic transactions." if made else "Synthetic data already exists.")
        if st.button("Delete all synthetic data"):
            execute("DELETE FROM transactions WHERE is_demo=1")
            log_action(user["id"],"DELETE_DEMO_DATA","Deleted all synthetic transactions")
            st.success("Synthetic data deleted.")

    with tab2:
        current=float(setting("plate_waste_kpi","20") or 20)
        kpi=st.number_input("Plate waste KPI (%)",min_value=0.0,max_value=100.0,value=current,step=1.0)
        if st.button("Save KPI"):
            set_setting("plate_waste_kpi",str(kpi))
            log_action(user["id"],"UPDATE_KPI",f"{kpi}%")
            st.success("KPI saved.")
        counts={
            "Facilities":fetchone("SELECT COUNT(*) n FROM facilities")["n"],
            "Service areas":fetchone("SELECT COUNT(*) n FROM service_areas")["n"],
            "Food items":fetchone("SELECT COUNT(*) n FROM food_items")["n"],
            "Ingredients":fetchone("SELECT COUNT(*) n FROM ingredients")["n"],
            "Recipes":fetchone("SELECT COUNT(*) n FROM recipes")["n"],
        }
        cols=st.columns(len(counts))
        for col,(label,value) in zip(cols,counts.items()):
            col.metric(label,value)

    with tab3:
        logs=fetchall(
            """SELECT a.created_at,COALESCE(u.username,'system') username,a.action,a.details
               FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 250"""
        )
        st.dataframe(logs,use_container_width=True,hide_index=True)
