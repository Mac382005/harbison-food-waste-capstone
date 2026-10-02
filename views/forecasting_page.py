from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.analytics import transactions_df
from src.forecasting import (
    context_frame,
    predict_plate_waste,
    predict_preparation,
    train_plate_waste_model,
    train_preparation_model,
)
from src.db import fetchall, fetchone, setting
from src.menu import menu_components, menu_items, menu_services, menu_variants, menu_week
from src.costing import recipe_cost


def _df_cache_key(df: pd.DataFrame):
    if df.empty:
        return (0, None, None, None, None)
    return (
        len(df),
        int(df.id.min()),
        int(df.id.max()),
        str(df.service_date.min()),
        str(df.service_date.max()),
    )


@st.cache_resource(show_spinner=False, hash_funcs={pd.DataFrame: _df_cache_key})
def _train_models(df: pd.DataFrame):
    return train_preparation_model(df), train_plate_waste_model(df)


def _metric_value(value, suffix=""):
    return "N/A" if value is None else f"{value:.2f}{suffix}"


def page():
    require_roles("admin", "manager", "dietitian")
    page_header(
        "DECISION SUPPORT",
        "ML Preparation & Meal-Quality Forecasting",
        "Train on menu-aligned synthetic data now, then move toward real Harbison observations as they become available.",
    )

    syn_n = fetchone("SELECT COUNT(*) n FROM transactions WHERE synthetic_run_id IS NOT NULL")["n"]
    real_n = fetchone("SELECT COUNT(*) n FROM transactions WHERE is_demo=0")["n"]
    badges = [("Harbison menu context", "source-green")]
    if syn_n:
        badges.append((f"Synthetic ML training: {syn_n:,} records", "source-blue"))
    if real_n:
        badges.append((f"Real records: {real_n:,}", "source-green"))
    badges.append(("Decision support — not automatic ordering", "source-orange"))
    render_source_badges(badges)

    source_options = []
    if syn_n:
        source_options.append("Synthetic ML data")
    if real_n:
        source_options.append("Real Harbison data")
    if syn_n and real_n:
        source_options.append("Real + synthetic")
    if not source_options:
        st.info("No training data is available yet. Generate a menu-aligned dataset in Synthetic ML Data or collect real waste records.")
        return

    source_label = st.selectbox("Training source", source_options, index=0)
    source_map = {
        "Synthetic ML data": "synthetic",
        "Real Harbison data": "real",
        "Real + synthetic": "combined",
    }
    df = transactions_df(source=source_map[source_label])

    if source_label == "Synthetic ML data":
        st.info(
            "Model results on this page are based on clearly labelled synthetic training data generated from the real Harbison menu structure. "
            "They demonstrate the ML workflow and should not be presented as measured Harbison performance."
        )
    elif source_label == "Real + synthetic":
        st.warning("Combined training mixes simulated and real observations. Use this only for experimentation; report real-only model results separately once enough real data exists.")

    try:
        with st.spinner("Training and evaluating time-split ML models..."):
            prep_model, plate_model = _train_models(df)
    except ValueError as exc:
        st.warning(str(exc))
        return

    st.subheader("Model evaluation")
    st.caption(
        f"Time-based holdout starts {prep_model.cutoff_date}. Training: {prep_model.train_rows:,} production rows; "
        f"test: {prep_model.test_rows:,}. This avoids a random train/test split across the same dates."
    )
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Preparation MAE", f"{prep_model.metrics['mae']:.2f} kg")
    e2.metric("Baseline MAE", f"{prep_model.metrics['baseline_mae']:.2f} kg")
    imp = prep_model.metrics.get("mae_improvement_pct")
    e3.metric("MAE improvement", "N/A" if imp is None else f"{imp:.1f}%")
    e4.metric("Preparation WAPE", _metric_value(prep_model.metrics.get("wape"), "%"), help="Weighted absolute percentage error across held-out preparation quantities.")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Plate-waste MAE", f"{plate_model.metrics['mae']:.2f} percentage points")
    p2.metric("Plate baseline MAE", f"{plate_model.metrics['baseline_mae']:.2f} pp")
    plate_imp = plate_model.metrics.get("mae_improvement_pct")
    p3.metric("Plate MAE improvement", "N/A" if plate_imp is None else f"{plate_imp:.1f}%")
    p4.metric("Plate-waste R²", _metric_value(plate_model.metrics.get("r2")))

    with st.expander("Model diagnostics", expanded=False):
        st.write(
            f"Preparation R²: {prep_model.metrics.get('r2', float('nan')):.3f} | "
            f"Preparation RMSE: {prep_model.metrics.get('rmse', float('nan')):.3f} kg | "
            f"Plate RMSE: {plate_model.metrics.get('rmse', float('nan')):.2f} percentage points"
        )
        st.caption(
            "For synthetic menu data, preparation R² can be high because food identity, portion size and resident count explain much of the scale. "
            "MAE, WAPE and improvement over the operational baseline are more useful headline measures for the prototype."
        )

    st.divider()
    st.subheader("Forecast a scheduled menu item")
    forecast_date = st.date_input("Service date", date.today() + timedelta(days=7), key="ml_forecast_date")
    variants = menu_variants(forecast_date)
    if not variants:
        st.warning("No Harbison menu schedule is available for this date.")
        return

    a, b, c = st.columns(3)
    default_variant = variants.index("Regular") if "Regular" in variants else 0
    variant = a.selectbox("Menu type", variants, index=default_variant)
    services = menu_services(forecast_date, variant)
    meal = b.selectbox("Meal service", services)
    components = menu_components(forecast_date, variant, meal)
    component = c.selectbox("Menu component", components)
    items = menu_items(forecast_date, meal, variant, component)
    if not items:
        st.warning("No scheduled food item is available for this selection.")
        return
    item_names = [x["name"] for x in items]
    food_name = st.selectbox("Scheduled food item", item_names)
    item = items[item_names.index(food_name)]

    facilities = sorted(df.facility.dropna().unique().tolist())
    if not facilities:
        st.warning("Training data has no facility context.")
        return
    d, e, f = st.columns(3)
    facility = d.selectbox("Facility / simulated site", facilities)
    area_options = sorted(df[df.facility.eq(facility)].service_area.dropna().unique().tolist())
    area = e.selectbox("Service area", area_options)

    hist = df[
        df.facility.eq(facility)
        & df.service_area.eq(area)
        & df.menu_variant.fillna("Unknown").eq(variant)
    ]
    default_residents = int(round(hist.resident_count.dropna().median())) if not hist.resident_count.dropna().empty else 50
    residents = f.number_input("Expected residents for this menu type", min_value=1, max_value=250, value=max(1, default_residents), step=1)

    context = context_frame(
        service_date=forecast_date,
        food_item=item["name"],
        category=item.get("category") or "Unknown",
        meal=meal,
        facility=facility,
        service_area=area,
        menu_variant=variant,
        menu_component=component,
        resident_count=int(residents),
        origin_date=df.service_date.min(),
    )
    prep_kg = predict_preparation(prep_model, context)
    plate_pct = predict_plate_waste(plate_model, context)
    kpi = float(setting("plate_waste_kpi", "20") or 20)

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Predicted preparation", f"{prep_kg:.2f} kg")
    r2.metric("Preparation per resident", f"{prep_kg / residents:.3f} kg")
    r3.metric("Predicted plate waste", f"{plate_pct:.1f}%")
    r4.metric("Meal-quality signal", "Above KPI" if plate_pct > kpi else "Within KPI", help=f"Configured plate-waste KPI: {kpi:.1f}%")

    recipe_meta = None
    linked_id = item.get("linked_recipe_food_item_id")
    if linked_id:
        recipe_meta = fetchone(
            "SELECT * FROM sponsor_recipes WHERE food_item_id=?",
            (linked_id,),
        )
    if recipe_meta:
        serving_kg = float(recipe_meta["serving_size_g"]) / 1000.0
        approx_serves = prep_kg / serving_kg if serving_kg > 0 else None
        batch_equiv = approx_serves / recipe_meta["serves"] if approx_serves is not None and recipe_meta["serves"] else None
        rc = recipe_cost(linked_id)
        x1, x2, x3 = st.columns(3)
        x1.metric("Approx. serves", "N/A" if approx_serves is None else f"{approx_serves:.0f}")
        x2.metric("Standard recipe batches", "N/A" if batch_equiv is None else f"{batch_equiv:.2f} ×")
        x3.metric("Estimated ingredient cost", "N/A" if not rc else f"A${prep_kg * rc['cost_per_kg']:,.2f}")

    st.caption(
        f"Menu context: Week {menu_week(forecast_date)} | {forecast_date.strftime('%A')} | {variant} | {meal} | {component}."
    )
    st.warning(
        "The model is decision support. Synthetic-data forecasts are for prototype validation and demonstration; staff should not use them as real ordering instructions."
    )
