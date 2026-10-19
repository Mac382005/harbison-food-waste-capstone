from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from src.auth import require_roles
from src.db import connection, fetchall
from src.intake import MEAL_LABELS, PLATE_MEALS
from src.intake_excel import build_report
from src.styles import page_header
from src.textures import texture_label

def _load(start: date, end: date, site_id: int | None, source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Low-intake items (with reasons) and nurse notes for current meal records in the period."""
    where = "o.is_current=1 AND o.data_source=? AND o.service_date BETWEEN ? AND ?"
    params: list = [source, start.isoformat(), end.isoformat()]
    if site_id:
        where += " AND o.facility_id=?"
        params.append(site_id)
    with connection() as c:
        items = pd.read_sql_query(
            f"""SELECT o.service_date AS Date, m.name AS meal, r.display_name AS Resident, r.room AS Room,
                       r.menu_variant AS diet, c.item_label AS Item, c.served_weight_g AS served_g, c.intake_pct AS eaten,
                       COALESCE(c.reason_uneaten, '') AS Reason, COALESCE(u.display_name, '') AS "Recorded by"
                FROM intake_component_observations c
                JOIN intake_meal_observations o ON o.id=c.observation_id
                JOIN intake_residents r ON r.id=o.resident_id
                JOIN meals m ON m.id=o.meal_id
                LEFT JOIN users u ON u.id=o.recorded_by
                WHERE {where} AND c.observed_status='observed' AND (c.intake_pct <= 50 OR c.reason_uneaten IS NOT NULL)
                ORDER BY o.service_date DESC, m.sort_order, r.room""", c, params=params)
        notes = pd.read_sql_query(
            f"""SELECT o.service_date AS Date, m.name AS meal, r.display_name AS Resident, r.room AS Room,
                       o.meal_status AS Outcome, o.staff_observation AS Note,
                       COALESCE(u.display_name, '') AS "Written by"
                FROM intake_meal_observations o
                JOIN intake_residents r ON r.id=o.resident_id
                JOIN meals m ON m.id=o.meal_id
                LEFT JOIN users u ON u.id=o.recorded_by
                WHERE {where} AND o.staff_observation IS NOT NULL AND TRIM(o.staff_observation)<>''
                ORDER BY o.service_date DESC, m.sort_order, r.room""", c, params=params)
    for df in (items, notes):
        if not df.empty:
            df["Meal"] = df.pop("meal").map(MEAL_LABELS)
    if not items.empty:
        items["Diet"] = items.pop("diet").map(texture_label)
        eaten_numeric = items["eaten"].astype(float)
        items["Served (g)"] = items.pop("served_g").round(1)
        items["Estimated eaten (g)"] = (items["Served (g)"] * eaten_numeric / 100).round(1)
        items["Eaten"] = items.pop("eaten").astype(int).astype(str) + "%"
        items = items[["Date", "Meal", "Resident", "Room", "Diet", "Item", "Served (g)", "Eaten",
                       "Estimated eaten (g)", "Reason", "Recorded by"]]
    if not notes.empty:
        notes["Outcome"] = notes["Outcome"].map({"served": "Ate", "refused": "Refused", "missed": "Not there"})
        notes = notes[["Date", "Meal", "Resident", "Room", "Outcome", "Note", "Written by"]]
    return items, notes


def page():
    user = require_roles("admin", "dietitian")
    page_header("RESIDENT MEAL & CONSUMPTION RECORDS", "Dietitian Review",
                "Why food was left, and the notes nurses wrote, in one place.")

    sites = fetchall("SELECT id, name FROM facilities WHERE active=1 ORDER BY name")
    source_rows = fetchall("SELECT data_source, COUNT(*) n FROM intake_residents WHERE active=1 GROUP BY data_source")
    source_counts = {r["data_source"]: r["n"] for r in source_rows}
    source_options = []
    if source_counts.get("real"):
        source_options.append("Real data")
    if source_counts.get("fictional_demo"):
        source_options.append("Synthetic data")
    if not source_options:
        source_options = ["Real data"]
    source_label = st.selectbox("Resident data source", source_options, key="rn_source") if len(source_options) > 1 else source_options[0]
    if len(source_options) == 1:
        st.caption(f"Resident data source: {source_label}")
    source = "real" if source_label == "Real data" else "fictional_demo"

    c1, c2, c3 = st.columns(3)
    start = c1.date_input("From", date.today() - timedelta(days=6), key="rn_start")
    end = c2.date_input("To", date.today(), key="rn_end")
    site = c3.selectbox("Site", [None] + [s["id"] for s in sites], key="rn_site",
                        format_func=lambda i: "All sites" if i is None else next(s["name"] for s in sites if s["id"] == i))
    d1, d2 = st.columns(2)
    meals = d1.multiselect("Meal", PLATE_MEALS, format_func=MEAL_LABELS.get, key="rn_meals",
                           placeholder="All meals")
    who = d2.text_input("Resident or room", key="rn_who", placeholder="e.g. Holmes or 129")

    items, notes = _load(start, end, site, source)

    def _filter(df):
        if df.empty:
            return df
        if meals:
            df = df[df["Meal"].isin([MEAL_LABELS[m] for m in meals])]
        if who.strip():
            text = who.strip().lower()
            df = df[df["Resident"].fillna("").str.lower().str.contains(text) | (df["Room"].astype(str) == text)]
        return df

    items, notes = _filter(items), _filter(notes)
    with_reason = items[items["Reason"] != ""] if not items.empty else items

    m1, m2, m3 = st.columns(3)
    m1.metric("Items eaten 50% or less", len(items))
    m2.metric("With a reason given", len(with_reason))
    m3.metric("Nurse notes", len(notes))

    filters = []
    if meals:
        filters.append("Meals: " + ", ".join(MEAL_LABELS[m] for m in meals))
    if who.strip():
        filters.append(f"Resident/room: {who.strip()}")
    site_name = "All sites" if site is None else next(s_["name"] for s_ in sites if s_["id"] == site)
    report = build_report(items, notes, {
        "period": f"{start:%d %b %Y} to {end:%d %b %Y}", "site": site_name,
        "filters": "; ".join(filters), "generated_by": user["display_name"]})
    st.download_button("Download Excel report", report, f"low_intake_report_{start}_{end}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary", icon=":material/download:")

    tab1, tab2, tab3 = st.tabs(["Reasons", "Low-intake items", "Notes"])
    with tab1:
        if with_reason.empty:
            st.caption("No reasons recorded for this selection.")
        else:
            counts = with_reason["Reason"].value_counts().rename_axis("Reason").reset_index(name="Times")
            st.plotly_chart(px.bar(counts.sort_values("Times"), x="Times", y="Reason", orientation="h",
                                   labels={"Reason": ""}), use_container_width=True)
            top_items = (with_reason.groupby(["Reason", "Item"]).size().rename("Times").reset_index()
                         .sort_values("Times", ascending=False).head(15))
            st.markdown("**Most common reason + item**")
            st.dataframe(top_items, hide_index=True, use_container_width=True)
    with tab2:
        if items.empty:
            st.caption("No items eaten 50% or less for this selection.")
        else:
            st.dataframe(items, hide_index=True, use_container_width=True)
            st.download_button("Download raw CSV", items.to_csv(index=False).encode("utf-8"),
                               f"low_intake_{start}_{end}.csv", "text/csv")
    with tab3:
        if notes.empty:
            st.caption("No notes written for this selection.")
        else:
            st.dataframe(notes, hide_index=True, use_container_width=True)
