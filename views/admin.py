import streamlit as st

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.db import fetchone, setting, set_setting, fetchall, log_action
from src.sponsor_import import sponsor_ingredient_coverage, retire_legacy_demo_data, import_default_sponsor_files
from src.menu_import import import_harbison_menu


def page():
    user = require_roles("admin")
    page_header(
        "SYSTEM",
        "Administration",
        "Harbison data readiness, KPI configuration and audit events. Synthetic data generation is disabled.",
    )
    render_source_badges([
        ("Sponsor-first mode", "source-green"),
        ("Synthetic generation disabled", "source-blue"),
    ])

    tab1, tab2, tab3 = st.tabs(["Data readiness", "KPI & system", "Audit log"])

    with tab1:
        real_tx = fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=0")["n"]
        demo_tx = fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=1")["n"]
        menu_rows = fetchone("SELECT COUNT(*) n FROM harbison_menu_schedule")["n"]
        sponsor_recipes = fetchone("SELECT COUNT(*) n FROM sponsor_recipes")["n"]
        supplier_rows = fetchone("SELECT COUNT(*) n FROM supplier_products")["n"]
        coverage = sponsor_ingredient_coverage()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Real waste records", real_tx)
        c2.metric("Real menu rows", menu_rows)
        c3.metric("Validated recipes", sponsor_recipes)
        c4.metric("Supplier rows", supplier_rows)
        c5.metric("Legacy demo records", demo_tx)

        p1, p2, p3 = st.columns(3)
        p1.metric("Recipe ingredient lines", coverage["recipe_lines"])
        p2.metric("Mapped costing lines", coverage["mapped_cost_lines"])
        p3.metric("Priced mapped ingredients", coverage["priced_cost_ingredients"])

        if st.button("Reconcile Harbison reference files", type="primary"):
            result = import_default_sponsor_files()
            menu_count = import_harbison_menu()
            log_action(user["id"], "RECONCILE_SPONSOR_DATA", f"{result}, menu={menu_count}")
            st.success(
                f"Reconciled {result['supplier_rows']} supplier rows, {result['recipes']} recipes, "
                f"{result['recipe_lines']} recipe lines, {result['cost_mapped_lines']} safe costing mappings "
                f"and {menu_count} menu rows."
            )
            st.rerun()

        if demo_tx > 0:
            st.warning("Legacy synthetic transactions still exist but are excluded from dashboards, reports and forecasting.")

        with st.expander("Retire old prototype-only data"):
            st.write(
                "This removes legacy synthetic transactions, the old made-up menu schedule and unused seeded prototype food/ingredient records. Harbison recipes and real records are protected."
            )
            confirm = st.checkbox("I understand this is permanent")
            if st.button("Retire legacy demo data", disabled=not confirm):
                removed = retire_legacy_demo_data()
                log_action(user["id"], "RETIRE_LEGACY_DEMO_DATA", str(removed))
                st.success(f"Legacy cleanup complete: {removed}")
                st.rerun()

    with tab2:
        current = float(setting("plate_waste_kpi", "20") or 20)
        kpi = st.number_input("Plate waste KPI (%)", min_value=0.0, max_value=100.0, value=current, step=1.0)
        if st.button("Save KPI"):
            set_setting("plate_waste_kpi", str(kpi))
            log_action(user["id"], "UPDATE_KPI", f"{kpi}%")
            st.success("KPI saved.")

        counts = {
            "Facilities": fetchone("SELECT COUNT(*) n FROM facilities")["n"],
            "Service areas": fetchone("SELECT COUNT(*) n FROM service_areas")["n"],
            "Harbison menu items": fetchone("SELECT COUNT(DISTINCT food_item_id) n FROM harbison_menu_schedule")["n"],
            "Cost ingredients": fetchone("SELECT COUNT(*) n FROM ingredients")["n"],
            "Costing recipes": fetchone("SELECT COUNT(*) n FROM recipes")["n"],
        }
        cols = st.columns(len(counts))
        for col, (label, value) in zip(cols, counts.items()):
            col.metric(label, value)

    with tab3:
        logs = fetchall(
            """SELECT a.created_at,COALESCE(u.username,'system') username,a.action,a.details
               FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 250"""
        )
        st.dataframe(logs, use_container_width=True, hide_index=True)
