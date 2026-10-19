import streamlit as st
from src.auth import require_roles
from src.styles import page_header
from src.analytics import transactions_df, filtered
from src.db import execute, log_action


def page():
    user = require_roles("admin", "manager", "kitchen", "dietitian")
    page_header("AUDITABLE DATA", "Transaction Log", "Review real Harbison waste entries, who recorded them, and export filtered records.")

    df = transactions_df(include_demo=False)
    if df.empty:
        st.info("No real transactions yet.")
        return

    c1, c2, c3 = st.columns(3)
    facility = c1.selectbox("Facility", ["All"] + sorted(df.facility.unique().tolist()))
    wtype = c2.selectbox("Waste type", ["All", "Production Waste", "Plate Waste"])
    food = c3.selectbox("Food item", ["All"] + sorted(df.food_item.unique().tolist()))
    fdf = filtered(df, facility=facility, waste_type=wtype, food=food)

    show = fdf[["id", "service_date", "facility", "service_area", "meal", "food_item", "waste_type", "waste_kg", "waste_percentage", "waste_reason", "waste_cost", "recorded_by"]].copy()
    show["service_date"] = show.service_date.dt.date
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.download_button(
        "Download filtered CSV", show.to_csv(index=False).encode(), "harbison_food_waste_transactions.csv", "text/csv"
    )

    if user["role"] in {"admin", "manager"}:
        with st.expander("Delete a transaction (manager/admin only)"):
            ids = fdf.id.astype(int).tolist()
            if ids:
                tid = st.selectbox("Transaction ID", ids)
                confirm = st.checkbox("Confirm permanent deletion")
                if st.button("Delete selected record", disabled=not confirm):
                    execute("DELETE FROM transactions WHERE id=?", (tid,))
                    log_action(user["id"], "DELETE_TRANSACTION", f"Deleted transaction {tid}")
                    st.success("Deleted. Reload this page to refresh.")
