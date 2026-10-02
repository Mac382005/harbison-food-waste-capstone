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
    ranked = df[~labels.isin(_GENERIC_SERVICE_LABELS)].copy()
    return ranked if not ranked.empty else df



def page():
    require_roles("admin", "manager", "dietitian")
    page_header(
        "MANAGEMENT",
        "Reports",
        "Daily, weekly and four-week-cycle views for real records or clearly-labelled synthetic ML data.",
    )
    render_source_badges([
        ("Real and synthetic sources separated", "source-green"),
        ("Synthetic data = model development only", "source-blue"),
    ])

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
        st.info("No waste data is available yet.")
        return
    source_label = st.selectbox("Data source", opts, index=0)
    source = {"Synthetic ML data": "synthetic", "Real Harbison data": "real", "Real + synthetic": "combined"}[source_label]
    df = transactions_df(source=source)
    if df.empty:
        st.info("No records are available for this source.")
        return
    if source == "synthetic":
        st.info("Report values below are simulated and should not be presented as measured Harbison outcomes.")

    c1, c2, c3, c4 = st.columns(4)
    facility = c1.selectbox("Facility", ["All"] + sorted(df.facility.unique().tolist()))
    area = c2.selectbox("Service area", ["All"] + sorted(df.service_area.unique().tolist()))
    meal = c3.selectbox("Meal", ["All"] + sorted(df.meal.unique().tolist()))
    wtype = c4.selectbox("Waste type", ["All", "Production Waste", "Plate Waste"])
    period = st.segmented_control("Report grouping", ["Daily", "Weekly", "4-week"], default="Weekly")
    fdf = filtered(df, facility=facility, area=area, meal=meal, waste_type=wtype)

    if fdf.empty:
        st.info("No records match the selected filters.")
        return

    kpi = float(setting("plate_waste_kpi", "20") or 20)
    plate = fdf[fdf.waste_type == "Plate Waste"]
    breaches = int((plate.waste_percentage.fillna(-1) > kpi).sum()) if not plate.empty else 0
    known_cost = fdf.waste_cost.dropna()

    a, b, c, d = st.columns(4)
    a.metric("Waste", f"{fdf.waste_kg.sum():.1f} kg")
    b.metric("Waste cost", "N/A" if known_cost.empty else money(known_cost.sum()))
    c.metric("Avg plate waste", fmt_pct(plate.waste_percentage.dropna().mean() if not plate.empty else None))
    breach_rate = (breaches / len(plate) * 100.0) if len(plate) else 0.0
    d.metric("KPI breach rate", f"{breach_rate:.1f}%", help=f"{breaches:,} of {len(plate):,} plate-waste observations exceeded {kpi:.1f}%.")

    temp = fdf.copy()
    if period == "Daily":
        temp["period"] = temp.service_date.dt.date.astype(str)
    elif period == "Weekly":
        temp["period"] = temp.service_date.dt.to_period("W").astype(str)
    else:
        origin = temp.service_date.min()
        temp["period_index"] = ((temp.service_date - origin).dt.days // 28) + 1
        temp["period"] = "Cycle " + temp["period_index"].astype(str)

    trend = temp.groupby(["period", "waste_type"], as_index=False).waste_kg.sum()
    st.plotly_chart(
        px.bar(trend, x="period", y="waste_kg", color="waste_type", barmode="group", title=f"{period} waste"),
        use_container_width=True,
    )

    left, right = st.columns(2)
    area_df = fdf.copy()
    area_df["area_label"] = area_df["facility"].astype(str) + " — " + area_df["service_area"].astype(str)
    by_area = area_df.groupby(["area_label", "waste_type"], as_index=False).waste_kg.sum()
    left.plotly_chart(
        px.bar(by_area, x="area_label", y="waste_kg", color="waste_type", title="Waste by facility / service area"),
        use_container_width=True,
    )

    if not plate.empty:
        quality_source = _rankable_items(plate.dropna(subset=["waste_percentage"]))
        quality = quality_source.groupby("food_item", as_index=False).agg(
            avg_plate_waste=("waste_percentage", "mean"), observations=("id", "count")
        ).sort_values("avg_plate_waste", ascending=False)
        quality = quality[quality.observations >= 3]
        if not quality.empty:
            quality["status"] = quality.avg_plate_waste.apply(lambda x: "Above KPI" if x > kpi else "Within KPI")
            right.plotly_chart(
                px.bar(
                    quality.head(12).sort_values("avg_plate_waste"),
                    x="avg_plate_waste", y="food_item", orientation="h", color="status", title="Meal-quality signals"
                ),
                use_container_width=True,
            )

    filename = "harbison_synthetic_report.csv" if source == "synthetic" else "harbison_food_waste_report.csv"
    st.download_button("Export report CSV", fdf.to_csv(index=False).encode(), filename, "text/csv")
