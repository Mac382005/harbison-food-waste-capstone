import streamlit as st
import plotly.express as px

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.analytics import transactions_df, filtered
from src.db import setting
from .common import money, fmt_pct


def page():
    require_roles("admin", "manager", "dietitian")
    page_header(
        "ANALYTICS",
        "Food Waste Dashboard",
        "Real Harbison waste records only. Recipe and ingredient costs support waste-cost estimates but are not counted as waste observations.",
    )
    render_source_badges([
        ("Real operational waste only", "source-green"),
        ("No synthetic transactions", "source-blue"),
    ])

    df = transactions_df(include_demo=False)
    if df.empty:
        st.info(
            "No real waste records have been entered yet. Use Record Waste or import future Harbison waste-history files; the dashboard will populate automatically."
        )
        return

    with st.expander("Filters", expanded=False):
        c1, c2, c3 = st.columns(3)
        start = c1.date_input("From", df.service_date.min().date())
        end = c2.date_input("To", df.service_date.max().date())
        facility = c3.selectbox("Facility", ["All"] + sorted(df.facility.unique().tolist()))
        area_opts = (
            ["All"] + sorted(df[df.facility.eq(facility)].service_area.unique().tolist())
            if facility != "All"
            else ["All"] + sorted(df.service_area.unique().tolist())
        )
        c4, c5, c6 = st.columns(3)
        area = c4.selectbox("Service area", area_opts)
        meal = c5.selectbox("Meal", ["All"] + sorted(df.meal.unique().tolist()))
        wtype = c6.selectbox("Waste type", ["All", "Production Waste", "Plate Waste"])

    fdf = filtered(df, facility=facility, area=area, meal=meal, waste_type=wtype, start=start, end=end)
    if fdf.empty:
        st.info("No real records match the selected filters.")
        return

    kpi = float(setting("plate_waste_kpi", "20") or 20)
    prod = fdf[fdf.waste_type == "Production Waste"]
    plate = fdf[fdf.waste_type == "Plate Waste"]
    breaches = int((plate.waste_percentage.fillna(-1) > kpi).sum()) if not plate.empty else 0
    breach_rate = (breaches / len(plate) * 100) if len(plate) else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total waste", f"{fdf.waste_kg.sum():.1f} kg")
    m2.metric("Waste cost", money(fdf.waste_cost.fillna(0).sum()))
    m3.metric("Average plate waste", fmt_pct(plate.waste_percentage.dropna().mean() if not plate.empty else None))
    m4.metric("KPI breach rate", f"{breach_rate:.1f}%", help=f"{breaches} of {len(plate)} plate-waste observations exceeded {kpi:.1f}%.")

    n1, n2, n3 = st.columns(3)
    n1.metric("Production waste", f"{prod.waste_kg.sum():.1f} kg")
    n2.metric("Plate waste", f"{plate.waste_kg.sum():.1f} kg")
    n3.metric("Average production waste", fmt_pct(prod.waste_percentage.dropna().mean() if not prod.empty else None))

    bydate = fdf.assign(day=fdf.service_date.dt.date).groupby(["day", "waste_type"], as_index=False).waste_kg.sum()
    st.plotly_chart(
        px.line(bydate, x="day", y="waste_kg", color="waste_type", markers=True, title="Waste over time"),
        use_container_width=True,
    )

    a, b = st.columns(2)
    total_food = fdf.groupby("food_item", as_index=False).waste_kg.sum().sort_values("waste_kg", ascending=False).head(10)
    a.plotly_chart(
        px.bar(total_food.sort_values("waste_kg"), x="waste_kg", y="food_item", orientation="h", title="Highest total waste (kg)"),
        use_container_width=True,
    )

    plate_valid = plate.dropna(subset=["waste_percentage"])
    if not plate_valid.empty:
        avg_plate = plate_valid.groupby("food_item", as_index=False).waste_percentage.mean().sort_values("waste_percentage", ascending=False).head(10)
        b.plotly_chart(
            px.bar(avg_plate.sort_values("waste_percentage"), x="waste_percentage", y="food_item", orientation="h", title="Highest average plate waste (%)"),
            use_container_width=True,
        )
    else:
        b.info("Plate-waste percentages will appear once served weights are recorded.")

    meal_group = fdf.groupby(["meal", "waste_type"], as_index=False).waste_kg.sum()
    st.plotly_chart(
        px.bar(meal_group, x="meal", y="waste_kg", color="waste_type", barmode="group", title="Waste by meal service"),
        use_container_width=True,
    )
