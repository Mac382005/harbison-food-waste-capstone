import streamlit as st
import plotly.express as px

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.analytics import transactions_df, filtered
from src.db import setting, fetchone
from .common import money, fmt_pct

_GENERIC_SERVICE_LABELS = {
    "harbison morning tea",
    "harbison afternoon tea",
    "morning tea",
    "afternoon tea",
}


def _rankable_items(df):
    if df.empty:
        return df
    labels = df["food_item"].fillna("").astype(str).str.strip().str.lower()
    keep = ~labels.isin(_GENERIC_SERVICE_LABELS)
    ranked = df[keep].copy()
    return ranked if not ranked.empty else df



def _source_selector():
    syn_n = fetchone("SELECT COUNT(*) n FROM transactions WHERE synthetic_run_id IS NOT NULL")["n"]
    real_n = fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=0")["n"]
    opts = []
    if syn_n:
        opts.append("Synthetic ML data")
    if real_n:
        opts.append("Real Harbison data")
    if syn_n and real_n:
        opts.append("Real + synthetic")
    if not opts:
        return None, None
    label = st.selectbox("Data source", opts, index=0)
    mode = {"Synthetic ML data": "synthetic", "Real Harbison data": "real", "Real + synthetic": "combined"}[label]
    return label, mode


def page():
    require_roles("admin", "manager", "dietitian")
    page_header(
        "ANALYTICS",
        "Food Waste Dashboard",
        "Explore real operational records or clearly-labelled synthetic ML data generated from the Harbison menu.",
    )
    render_source_badges([
        ("Harbison menu context", "source-green"),
        ("Synthetic data supported for model development", "source-blue"),
        ("Real and synthetic records stay separate", "source-orange"),
    ])

    source_label, source_mode = _source_selector()
    if not source_mode:
        st.info("No waste records are available. Generate a Synthetic ML Dataset or enter/import real Harbison waste records.")
        return
    if source_mode == "synthetic":
        st.info("This dashboard is showing simulated records for prototype analysis and ML development, not measured Harbison waste.")
    elif source_mode == "combined":
        st.warning("This view combines simulated and real data. Keep them separate when reporting measured Harbison outcomes.")

    df = transactions_df(source=source_mode)
    if df.empty:
        st.info("No records are available for the selected data source.")
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
        c4, c5, c6, c7 = st.columns(4)
        area = c4.selectbox("Service area", area_opts)
        meal = c5.selectbox("Meal", ["All"] + sorted(df.meal.unique().tolist()))
        wtype = c6.selectbox("Waste type", ["All", "Production Waste", "Plate Waste"])
        variants = [x for x in sorted(df.menu_variant.dropna().unique().tolist()) if x]
        variant = c7.selectbox("Menu type", ["All"] + variants)

    fdf = filtered(
        df, facility=facility, area=area, meal=meal, waste_type=wtype,
        start=start, end=end, menu_variant=variant,
    )
    if fdf.empty:
        st.info("No records match the selected filters.")
        return

    kpi = float(setting("plate_waste_kpi", "20") or 20)
    prod = fdf[fdf.waste_type == "Production Waste"]
    plate = fdf[fdf.waste_type == "Plate Waste"]
    breaches = int((plate.waste_percentage.fillna(-1) > kpi).sum()) if not plate.empty else 0
    breach_rate = (breaches / len(plate) * 100) if len(plate) else 0

    known_cost = fdf.waste_cost.dropna()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total waste", f"{fdf.waste_kg.sum():.1f} kg")
    m2.metric("Waste cost", "N/A" if known_cost.empty else money(known_cost.sum()))
    m3.metric("Average plate waste", fmt_pct(plate.waste_percentage.dropna().mean() if not plate.empty else None))
    m4.metric("KPI breach rate", f"{breach_rate:.1f}%", help=f"{breaches} of {len(plate)} plate-waste observations exceeded {kpi:.1f}%.")

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Production waste", f"{prod.waste_kg.sum():.1f} kg")
    n2.metric("Plate waste", f"{plate.waste_kg.sum():.1f} kg")
    n3.metric("Average production waste", fmt_pct(prod.waste_percentage.dropna().mean() if not prod.empty else None))
    n4.metric("Observations", f"{len(fdf):,}")

    bydate = fdf.assign(day=fdf.service_date.dt.date).groupby(["day", "waste_type"], as_index=False).waste_kg.sum()
    st.plotly_chart(
        px.line(bydate, x="day", y="waste_kg", color="waste_type", title="Waste over time"),
        use_container_width=True,
    )

    a, b = st.columns(2)
    item_df = _rankable_items(fdf)
    total_food = item_df.groupby("food_item", as_index=False).waste_kg.sum().sort_values("waste_kg", ascending=False).head(12)
    a.plotly_chart(
        px.bar(total_food.sort_values("waste_kg"), x="waste_kg", y="food_item", orientation="h", title="Highest total waste (kg)"),
        use_container_width=True,
    )

    plate_valid = _rankable_items(plate.dropna(subset=["waste_percentage"]))
    if not plate_valid.empty:
        avg_plate = plate_valid.groupby("food_item", as_index=False).agg(
            waste_percentage=("waste_percentage", "mean"), observations=("id", "count")
        )
        avg_plate = avg_plate[avg_plate.observations >= 3].sort_values("waste_percentage", ascending=False).head(12)
        b.plotly_chart(
            px.bar(avg_plate.sort_values("waste_percentage"), x="waste_percentage", y="food_item", orientation="h", title="Highest average plate waste (%)"),
            use_container_width=True,
        )
    else:
        b.info("Plate-waste percentages will appear once served weights are available.")

    meal_group = fdf.groupby(["meal", "waste_type"], as_index=False).waste_kg.sum()
    st.plotly_chart(
        px.bar(meal_group, x="meal", y="waste_kg", color="waste_type", barmode="group", title="Waste by meal service"),
        use_container_width=True,
    )
