from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px

from src.auth import require_roles
from src.styles import page_header
from src.analytics import SOURCE_MODES, available_sources, transactions_df, filtered
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
        "Daily, weekly and four-week-cycle views using either real food-waste records or synthetic data.",
    )

    opts = available_sources()
    if not opts:
        st.info("No waste data is available yet.")
        return
    source_label = st.selectbox("Data source", opts, index=0)
    source = SOURCE_MODES[source_label]
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
    period = st.segmented_control("Report grouping", ["Daily", "Weekly", "4-week"], default="Weekly") or "Weekly"
    fdf = filtered(df, facility=facility, area=area, meal=meal, waste_type=wtype)

    if fdf.empty:
        st.info("No records match the selected filters.")
        return

    kpi = float(setting("plate_waste_kpi", "20") or 20)

    temp = fdf.copy()
    if period == "Daily":
        temp["period"] = temp.service_date.dt.date.astype(str)
        temp["period_end"] = temp.service_date.dt.normalize()
    elif period == "Weekly":
        weeks = temp.service_date.dt.to_period("W")
        temp["period"] = weeks.astype(str)
        temp["period_end"] = weeks.dt.end_time.dt.normalize()
    else:
        origin = temp.service_date.min().normalize()
        temp["period_index"] = ((temp.service_date - origin).dt.days // 28) + 1
        temp["period"] = "Cycle " + temp["period_index"].astype(str)
        temp["period_end"] = origin + pd.to_timedelta(temp["period_index"] * 28 - 1, unit="D")

    # Headline numbers follow the grouping: latest complete period vs the one before it.
    order = temp.groupby("period").period_end.max().sort_values()
    complete = order[order < pd.Timestamp(date.today())]
    all_periods = list(order.index)
    default = complete.index[-1] if not complete.empty else all_periods[-1]
    newest_first = all_periods[::-1]
    current = st.selectbox(
        "Show", newest_first, index=newest_first.index(default), key=f"rp_pick_{period}",
        format_func=lambda p_: p_ + ("  (in progress)" if order[p_] >= pd.Timestamp(date.today()) else ""))
    pos = all_periods.index(current)
    previous = all_periods[pos - 1] if pos > 0 else None

    def _numbers(part):
        plate = part[part.waste_type == "Plate Waste"]
        rated = plate.waste_percentage.dropna()
        cost = part.waste_cost.dropna()
        return {
            "kg": part.waste_kg.sum(),
            "cost": cost.sum() if not cost.empty else None,
            "plate_pct": rated.mean() if not rated.empty else None,
            "breach": (rated > kpi).mean() * 100 if not rated.empty else None,
            "breaches": int((rated > kpi).sum()),
            "plate_n": len(rated),
        }

    cur = _numbers(temp[temp.period == current])
    prev = _numbers(temp[temp.period == previous]) if previous else None

    def _delta(key, fmt):
        if not prev or cur[key] is None or prev[key] is None:
            return None
        return fmt(cur[key] - prev[key])

    label = {"Daily": "Day", "Weekly": "Week", "4-week": "4 weeks"}[period]
    st.markdown(f"**{label}: {current}**" + (f" · compared with {previous}" if previous else ""))
    a, b, c, d = st.columns(4)
    a.metric("Waste", f"{cur['kg']:.1f} kg", _delta("kg", lambda v: f"{v:+.1f} kg"), delta_color="inverse")
    b.metric("Waste cost", money(cur["cost"]), _delta("cost", lambda v: f"{v:+,.2f}"), delta_color="inverse")
    c.metric("Avg plate waste", fmt_pct(cur["plate_pct"]), _delta("plate_pct", lambda v: f"{v:+.1f} pts"),
             delta_color="inverse")
    d.metric("KPI breach rate", fmt_pct(cur["breach"]), _delta("breach", lambda v: f"{v:+.1f} pts"),
             delta_color="inverse",
             help=f"{cur['breaches']:,} of {cur['plate_n']:,} plate-waste observations exceeded {kpi:.1f}%.")
    all_cost = fdf.waste_cost.dropna()
    st.caption(f"All dates: {fdf.waste_kg.sum():.1f} kg"
               + ("" if all_cost.empty else f" · {money(all_cost.sum())}")
               + f" · {fdf.service_date.min():%d %b} to {fdf.service_date.max():%d %b %Y}")
    plate = fdf[fdf.waste_type == "Plate Waste"]

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
