from datetime import date, timedelta

import plotly.express as px
import streamlit as st

from src.auth import require_roles
from src.analytics import transactions_df
from src.db import fetchone, log_action
from src.styles import page_header

_GENERIC_SERVICE_LABELS = {
    "harbison morning tea",
    "harbison afternoon tea",
    "morning tea",
    "afternoon tea",
}

from src.synthetic_intake import clear_synthetic_resident_data, generate_synthetic_resident_data
from src.synthetic_data import (
    GenerationConfig,
    clear_synthetic_ml_data,
    estimate_transaction_count,
    generate_synthetic_ml_data,
    synthetic_summary,
)


def page():
    user = require_roles("admin", "manager")
    page_header(
        "MODEL DEVELOPMENT",
        "Synthetic Data",
        "Generate one consistent synthetic dataset for waste analysis, ML forecasting, and synthetic resident meal-record testing.",
    )

    summary = synthetic_summary()
    demo_residents = fetchone("SELECT COUNT(*) n FROM intake_residents WHERE data_source='fictional_demo' AND active=1")["n"]
    demo_meals = fetchone("SELECT COUNT(*) n FROM intake_meal_observations WHERE data_source='fictional_demo' AND is_current=1")["n"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Synthetic waste records", f"{summary['transactions']:,}")
    m2.metric("Synthetic residents", f"{demo_residents:,}")
    m3.metric("Resident meal records", f"{demo_meals:,}")
    m4.metric("Menu foods", summary["foods"])
    if summary["start_date"]:
        st.caption(f"Current synthetic range: {summary['start_date']} to {summary['end_date']}")

    with st.expander("Generate / replace synthetic data", expanded=summary["transactions"] == 0):
        st.write(
            "One action now generates both the menu-aligned synthetic food-waste history used by the ML model "
            "and synthetic resident meal/consumption records used to test the resident workflow. "
            "Both remain clearly synthetic and separate from real operational records."
        )
        c1, c2 = st.columns(2)
        start = c1.date_input("Start date", date(2026, 3, 1), key="syn_start")
        end = c2.date_input("End date", date(2026, 9, 30), key="syn_end")

        c3, c4, c5 = st.columns(3)
        resident_min = c3.number_input("Residents per dining area (min)", 20, 200, 44, 1)
        resident_max = c4.number_input("Residents per dining area (max)", 20, 220, 56, 1)
        seed = c5.number_input("Random seed", 1, 999999, 42, 1)

        d1, d2 = st.columns(2)
        intake_days = d1.number_input("Resident-record history (days)", 7, 120, 30, 1)
        residents_per_area = d2.number_input("Synthetic residents per dining area", 4, 50, 12, 1)

        active_locations = fetchone(
            """SELECT COUNT(*) n FROM facilities f JOIN service_areas sa ON sa.facility_id=f.id
               WHERE f.active=1 AND sa.active=1"""
        )["n"]
        f1, f2 = st.columns(2)
        fallback_facilities = f1.number_input("Synthetic sites if no locations exist", 1, 4, 2, 1)
        fallback_areas = f2.number_input("Dining areas per synthetic site", 1, 4, 2, 1)
        effective_locations = int(active_locations) if active_locations else int(fallback_facilities * fallback_areas)
        estimate = estimate_transaction_count(start, end, effective_locations)
        st.info(
            f"Estimated dataset size: approximately **{estimate:,} transactions** across {effective_locations} service areas. "
            "Each scheduled menu item produces one production-waste and one plate-waste observation."
        )
        replace = st.checkbox("Replace existing synthetic data", value=True)

        if st.button("Generate synthetic data", type="primary", use_container_width=True):
            if end < start:
                st.error("End date must be on or after start date.")
            elif resident_max < resident_min:
                st.error("Maximum residents must be greater than or equal to minimum residents.")
            else:
                with st.spinner("Generating menu-aligned waste data and synthetic resident records..."):
                    result = generate_synthetic_ml_data(
                        GenerationConfig(
                            start_date=start,
                            end_date=end,
                            seed=int(seed),
                            resident_min=int(resident_min),
                            resident_max=int(resident_max),
                            fallback_facilities=int(fallback_facilities),
                            fallback_areas_per_facility=int(fallback_areas),
                            replace_existing=replace,
                        )
                    )
                    intake_end = min(end, date.today() - timedelta(days=1))
                    if intake_end >= start:
                        intake_start = max(start, intake_end - timedelta(days=int(intake_days) - 1))
                        intake_result = generate_synthetic_resident_data(
                            intake_start, intake_end, residents_per_area=int(residents_per_area), seed=int(seed)
                        )
                    else:
                        intake_result = {"residents": 0, "orders": 0, "meals_recorded": 0, "items_recorded": 0}
                log_action(user["id"], "GENERATE_SYNTHETIC_DATA", f"waste={result}; intake={intake_result}")
                st.success(
                    f"Generated {result['transactions']:,} synthetic food-waste transactions and "
                    f"{intake_result['meals_recorded']:,} synthetic resident meal records."
                )
                if result["created_fallback_locations"]:
                    st.warning("No configured real locations existed, so placeholder locations (Harbison Site 1, Dining Area 1...) were created for model testing.")
                st.rerun()

    if summary["transactions"]:
        df = transactions_df(source="synthetic")
        st.subheader("Synthetic waste-data quality check")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Production rows", f"{len(df[df.waste_type.eq('Production Waste')]):,}")
        q2.metric("Plate rows", f"{len(df[df.waste_type.eq('Plate Waste')]):,}")
        q3.metric("Avg production waste", f"{df[df.waste_type.eq('Production Waste')].waste_percentage.mean():.1f}%")
        q4.metric("Avg plate waste", f"{df[df.waste_type.eq('Plate Waste')].waste_percentage.mean():.1f}%")

        a, b = st.columns(2)
        by_variant = df.groupby(["menu_variant", "waste_type"], as_index=False).waste_percentage.mean()
        a.plotly_chart(
            px.bar(by_variant, x="menu_variant", y="waste_percentage", color="waste_type", barmode="group", title="Average waste % by menu type"),
            use_container_width=True,
        )
        plate = df[df.waste_type.eq("Plate Waste")].copy()
        labels = plate.food_item.fillna("").astype(str).str.strip().str.lower()
        plate = plate[~labels.isin(_GENERIC_SERVICE_LABELS)]
        top = plate.groupby("food_item", as_index=False).agg(
            avg_plate_waste=("waste_percentage", "mean"), observations=("id", "count")
        )
        top = top[top.observations >= 10].sort_values("avg_plate_waste", ascending=False).head(12)
        b.plotly_chart(
            px.bar(top.sort_values("avg_plate_waste"), x="avg_plate_waste", y="food_item", orientation="h", title="Synthetic high plate-waste signals"),
            use_container_width=True,
        )

        st.download_button(
            "Download synthetic waste CSV",
            df.to_csv(index=False).encode("utf-8"),
            "harbison_synthetic_ml_dataset.csv",
            "text/csv",
        )

        with st.expander("Delete synthetic data"):
            st.warning("This deletes generated synthetic waste records and synthetic generated resident records. Real records are not touched.")
            confirm = st.checkbox("Confirm deletion of synthetic data")
            if st.button("Delete synthetic data", disabled=not confirm):
                removed = clear_synthetic_ml_data()
                clear_synthetic_resident_data()
                log_action(user["id"], "CLEAR_SYNTHETIC_DATA", f"Removed {removed} waste rows and synthetic resident intake records")
                st.success(f"Removed {removed:,} synthetic waste rows and synthetic resident records.")
                st.rerun()
