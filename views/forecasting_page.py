import streamlit as st

from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.analytics import transactions_df
from src.forecasting import forecast
from src.db import fetchone
from src.costing import recipe_cost


def page():
    require_roles("admin", "manager", "dietitian")
    page_header(
        "DECISION SUPPORT",
        "Preparation Forecasting",
        "Forecasting uses real production-waste history only and remains unavailable until enough Harbison observations exist.",
    )
    render_source_badges([
        ("Real waste history only", "source-green"),
        ("No synthetic training data", "source-blue"),
        ("Decision support — not automatic ordering", "source-orange"),
    ])

    df = transactions_df(include_demo=False)
    prod = df[df.waste_type == "Production Waste"].copy() if not df.empty else None
    if prod is None or prod.empty:
        st.info(
            "No real production-waste history is available yet. Continue collecting Harbison waste records; forecasting will activate when enough observations exist."
        )
        return

    c1, c2, c3 = st.columns(3)
    food = c1.selectbox("Food item", sorted(prod.food_item.unique().tolist()))
    meals = sorted(prod[prod.food_item == food].meal.unique().tolist())
    meal = c2.selectbox("Meal", meals)
    areas = ["All"] + sorted(prod[(prod.food_item == food) & (prod.meal == meal)].service_area.unique().tolist())
    area = c3.selectbox("Service area", areas)

    result = forecast(df, food, meal, area)
    x1, x2, x3 = st.columns(3)
    x1.metric("Real observations", result["n"])
    x2.metric("Recent usable requirement", "N/A" if result["avg"] is None else f"{result['avg']:.2f} kg")
    x3.metric("Recommended preparation", "N/A" if result["rec"] is None else f"{result['rec']:.2f} kg")
    st.info(result["message"])

    if result["baseline_mae"] is not None:
        st.write(f"Baseline MAE: **{result['baseline_mae']:.2f} kg**")
    if result["model_mae"] is not None:
        st.write(f"Random Forest evaluation MAE: **{result['model_mae']:.2f} kg**")

    if result["rec"] is not None:
        meta = fetchone(
            """SELECT sr.*,fi.id food_item_id FROM sponsor_recipes sr
               JOIN food_items fi ON fi.id=sr.food_item_id WHERE fi.name=?""",
            (food,),
        )
        if meta:
            serving_kg = meta["serving_size_g"] / 1000.0
            recommended_serves = result["rec"] / serving_kg if serving_kg > 0 else None
            batch_equiv = recommended_serves / meta["serves"] if recommended_serves is not None and meta["serves"] else None
            rc = recipe_cost(meta["food_item_id"])
            f1, f2, f3 = st.columns(3)
            f1.metric("Approx. serves", "N/A" if recommended_serves is None else f"{recommended_serves:.0f}")
            f2.metric("Standard-recipe batches", "N/A" if batch_equiv is None else f"{batch_equiv:.2f} ×")
            f3.metric("Estimated food cost", "N/A" if not rc else f"A${result['rec'] * rc['cost_per_kg']:,.2f}")
            yield_loss = "N/A" if meta["yield_loss_pct"] is None else f"{meta['yield_loss_pct']:.0f}%"
            st.caption(
                f"Harbison recipe reference: {meta['serves']} serves at {meta['serving_size_g']:.0f} g per serve; listed yield loss {yield_loss}."
            )

    st.warning("Forecasting is advisory. Staff should review resident demand, menu context and operational constraints before changing preparation or ordering quantities.")
