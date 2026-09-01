import streamlit as st
from src.auth import require_roles
from src.styles import page_header
from src.analytics import transactions_df
from src.forecasting import forecast


def page():
    require_roles("admin","manager","dietitian")
    page_header("DECISION SUPPORT", "Preparation Forecasting", "A conservative prototype that becomes more credible as real historical data accumulates.")

    df=transactions_df()
    prod=df[df.waste_type=="Production Waste"].copy() if not df.empty else None
    if prod is None or prod.empty:
        st.info("No production-waste history yet.")
        return

    c1,c2,c3=st.columns(3)
    food=c1.selectbox("Food item",sorted(prod.food_item.unique().tolist()))
    meals=sorted(prod[prod.food_item==food].meal.unique().tolist())
    meal=c2.selectbox("Meal",meals)
    areas=["All"]+sorted(prod[(prod.food_item==food)&(prod.meal==meal)].service_area.unique().tolist())
    area=c3.selectbox("Service area",areas)

    result=forecast(df,food,meal,area)
    x1,x2,x3=st.columns(3)
    x1.metric("Historical observations",result["n"])
    x2.metric("Recent usable requirement","N/A" if result["avg"] is None else f"{result['avg']:.2f} kg")
    x3.metric("Recommended preparation","N/A" if result["rec"] is None else f"{result['rec']:.2f} kg")
    st.info(result["message"])
    if result["baseline_mae"] is not None:
        st.write(f"Baseline MAE: **{result['baseline_mae']:.2f} kg**")
    if result["model_mae"] is not None:
        st.write(f"Random Forest evaluation MAE: **{result['model_mae']:.2f} kg**")
    st.warning("Forecasting is advisory. It should not automatically place orders or reduce food provision without staff review.")
