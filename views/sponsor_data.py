from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.auth import require_roles
from src.styles import page_header, render_legend, render_source_badges
from src.db import fetchall, fetchone, log_action
from src.sponsor_import import (
    import_default_sponsor_files,
    SUPPLIER_FILE,
    RECIPE_FILE,
    RECIPE_INGREDIENT_FILE,
)
from src.menu_import import MENU_FILE, import_harbison_menu
from src.real_data_import import validate_waste_dataframe, import_waste_dataframe

SUPPLIER_COLOURS = {
    "PFD": "#1f77b4",
    "Superior Foods": "#2ca02c",
    "SFD": "#ff7f0e",
    "No quote": "#9aa0a6",
}


def _supplier_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    price_cols = ["PFD", "Superior Foods", "SFD"]
    work["Lowest listed price"] = work[price_cols].min(axis=1, skipna=True)
    work["Highest listed price"] = work[price_cols].max(axis=1, skipna=True)
    work["Price spread"] = work["Highest listed price"] - work["Lowest listed price"]
    work["Quotes available"] = work[price_cols].notna().sum(axis=1)

    def lowest_supplier(row):
        vals = {c: row[c] for c in price_cols if pd.notna(row[c])}
        return min(vals, key=vals.get) if vals else "No quote"

    work["Lowest listed supplier"] = work.apply(lowest_supplier, axis=1)
    return work


def _build_spread_chart(df: pd.DataFrame):
    chart_df = (
        df.dropna(subset=["Price spread"])
        .nlargest(15, "Price spread")
        .sort_values("Price spread", ascending=True)
    )
    if chart_df.empty:
        return None
    fig = px.bar(
        chart_df,
        x="Price spread",
        y="Product",
        color="Lowest listed supplier",
        orientation="h",
        text="Price spread",
        color_discrete_map=SUPPLIER_COLOURS,
        custom_data=["Lowest listed price", "Highest listed price", "Category"],
    )
    fig.update_traces(
        texttemplate="A$%{x:.2f}",
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>Category: %{customdata[2]}<br>"
            "Price spread: A$%{x:.2f}<br>"
            "Lowest listed price: A$%{customdata[0]:.2f}<br>"
            "Highest listed price: A$%{customdata[1]:.2f}<extra></extra>"
        ),
    )
    fig.update_layout(
        height=620,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Price spread (AUD)",
        yaxis_title="",
        legend_title="Lowest listed quote",
        bargap=0.24,
    )
    return fig


def _build_quote_comparison_chart(df: pd.DataFrame):
    top = df.dropna(subset=["Price spread"]).nlargest(10, "Price spread")
    if top.empty:
        return None
    long_df = top.melt(
        id_vars=["Product"],
        value_vars=["PFD", "Superior Foods", "SFD"],
        var_name="Supplier",
        value_name="Price",
    ).dropna(subset=["Price"])
    fig = px.bar(
        long_df,
        x="Product",
        y="Price",
        color="Supplier",
        barmode="group",
        color_discrete_map=SUPPLIER_COLOURS,
        text="Price",
    )
    fig.update_traces(texttemplate="A$%{y:.2f}", textposition="outside")
    fig.update_layout(
        height=520,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Product",
        yaxis_title="Listed price (AUD)",
        legend_title="Supplier",
    )
    return fig


def _build_supplier_mix_chart(df: pd.DataFrame):
    if df.empty:
        return None
    mix = (
        df["Lowest listed supplier"]
        .fillna("No quote")
        .value_counts()
        .rename_axis("Supplier")
        .reset_index(name="Products")
    )
    fig = go.Figure(
        data=[
            go.Pie(
                labels=mix["Supplier"],
                values=mix["Products"],
                hole=0.5,
                marker=dict(colors=[SUPPLIER_COLOURS.get(x, "#9aa0a6") for x in mix["Supplier"]]),
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    return fig


def _read_upload(uploaded):
    if uploaded is None:
        return None
    return pd.read_excel(uploaded) if uploaded.name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(uploaded)


def _save_csv(uploaded, target):
    df = _read_upload(uploaded)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)
    return len(df)


def page():
    user = require_roles("admin", "manager", "dietitian")
    page_header(
        "HARBISON DATA",
        "Supplier, Menu, Recipes & Imports",
        "Use Harbison reference data for menu planning, recipe costing and supplier comparison without turning the app into a supplier recommendation tool.",
    )
    render_source_badges(
        [
            ("Harbison supplier reference", "source-green"),
            ("Real four-week menu", "source-blue"),
            ("Validated recipes", "source-orange"),
        ]
    )

    tab_supplier, tab_menu, tab_recipes, tab_import = st.tabs(
        ["Supplier comparison", "Menu overview", "Recipes", "Import updates"]
    )

    with tab_supplier:
        rows = fetchall(
            """SELECT category,product_name,pfd_price,superior_foods_price,sfd_price,source_page
               FROM supplier_products ORDER BY category,product_name"""
        )
        if not rows:
            st.info("No supplier comparison data has been imported yet.")
        else:
            df = pd.DataFrame(rows).rename(
                columns={
                    "category": "Category",
                    "product_name": "Product",
                    "pfd_price": "PFD",
                    "superior_foods_price": "Superior Foods",
                    "sfd_price": "SFD",
                    "source_page": "Source page",
                }
            )
            df = _supplier_summary(df)
            f1, f2 = st.columns([1, 2])
            categories = ["All"] + sorted(x for x in df["Category"].dropna().unique().tolist())
            category = f1.selectbox("Category", categories)
            search = f2.text_input("Search product", placeholder="e.g. butter, stock, flour")
            filtered = df.copy()
            if category != "All":
                filtered = filtered[filtered["Category"] == category]
            if search.strip():
                filtered = filtered[filtered["Product"].str.contains(search.strip(), case=False, na=False)]

            quoted = filtered[["PFD", "Superior Foods", "SFD"]].notna().sum(axis=1)
            avg_spread = filtered["Price spread"].dropna().mean() if filtered["Price spread"].notna().any() else None
            a, b, c = st.columns(3)
            a.metric("Products", len(filtered))
            b.metric("Products with 2+ quotes", int((quoted >= 2).sum()))
            c.metric("Average price spread", f"A${avg_spread:,.2f}" if avg_spread is not None else "N/A")

            st.caption(
                "Supplier data is retained for comparison and reporting only. The prototype does not recommend a supplier or automatically apply quotes to recipe costing."
            )
            render_legend(
                [
                    ("PFD", SUPPLIER_COLOURS["PFD"]),
                    ("Superior Foods", SUPPLIER_COLOURS["Superior Foods"]),
                    ("SFD", SUPPLIER_COLOURS["SFD"]),
                ]
            )

            left, right = st.columns([1.7, 1])
            with left:
                st.subheader("Largest listed price differences")
                fig = _build_spread_chart(filtered)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)
            with right:
                st.subheader("Lowest listed quote mix")
                fig = _build_supplier_mix_chart(filtered)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)

            st.subheader("Quote comparison for high-spread products")
            fig = _build_quote_comparison_chart(filtered)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

            display_cols = [
                "Category", "Product", "PFD", "Superior Foods", "SFD",
                "Lowest listed supplier", "Lowest listed price", "Highest listed price",
                "Price spread", "Source page",
            ]
            st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

    with tab_menu:
        total = fetchone("SELECT COUNT(*) n FROM harbison_menu_schedule")["n"]
        variants = fetchone("SELECT COUNT(DISTINCT menu_variant) n FROM harbison_menu_schedule")["n"]
        foods = fetchone("SELECT COUNT(DISTINCT food_item_id) n FROM harbison_menu_schedule")["n"]
        linked = fetchone(
            "SELECT COUNT(*) n FROM harbison_menu_schedule WHERE linked_recipe_food_item_id IS NOT NULL"
        )["n"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Menu rows", total)
        c2.metric("Menu types", variants)
        c3.metric("Unique menu items", foods)
        c4.metric("Recipe-linked rows", linked)
        st.caption("Regular, Soft Bite Sized, Minced and Puree menus are loaded across Weeks 1-4.")
        sample = fetchall(
            """SELECT menu_variant,week_number,day_name,meal_service,component,menu_label,linked_recipe_name
               FROM harbison_menu_schedule
               ORDER BY week_number,day_of_week,meal_service LIMIT 80"""
        )
        st.dataframe(pd.DataFrame(sample), use_container_width=True, hide_index=True)

    with tab_recipes:
        recipes = fetchall(
            """SELECT sr.recipe_name,fc.name category,sr.serves,sr.serving_size_g,
                      sr.yield_loss_pct,sr.allergens,sr.source_document,sr.source_page
               FROM sponsor_recipes sr
               JOIN food_items fi ON fi.id=sr.food_item_id
               LEFT JOIN food_categories fc ON fc.id=fi.category_id
               ORDER BY category,sr.recipe_name"""
        )
        soups = sum(1 for r in recipes if r.get("category") == "Soup")
        desserts = sum(1 for r in recipes if r.get("category") == "Dessert")
        a, b, c = st.columns(3)
        a.metric("Validated recipes", len(recipes))
        b.metric("Soups", soups)
        c.metric("Desserts added", desserts)
        st.info(
            "Only dessert recipes with sufficiently clear serving/yield information are used as authoritative costing recipes. Incomplete source pages are not forced into the system."
        )
        st.dataframe(pd.DataFrame(recipes), use_container_width=True, hide_index=True)

    with tab_import:
        st.subheader("Reference updates")
        s1 = st.file_uploader("Supplier comparison CSV / Excel", type=["csv", "xlsx", "xls"], key="supplier")
        r1 = st.file_uploader("Recipe master CSV / Excel", type=["csv", "xlsx", "xls"], key="recipes")
        r2 = st.file_uploader("Recipe ingredient lines CSV / Excel", type=["csv", "xlsx", "xls"], key="recipe_lines")
        menu = st.file_uploader("Four-week menu CSV", type=["csv"], key="menu")
        if st.button("Import reference updates", disabled=not any([s1, r1, r2, menu])):
            if s1:
                _save_csv(s1, SUPPLIER_FILE)
            if r1:
                _save_csv(r1, RECIPE_FILE)
            if r2:
                _save_csv(r2, RECIPE_INGREDIENT_FILE)
            if menu:
                _save_csv(menu, MENU_FILE)
            result = import_default_sponsor_files()
            m = import_harbison_menu()
            log_action(user["id"], "IMPORT_REFERENCE_UPDATE", f"{result}, menu={m}")
            st.success(
                f"Imported {result['supplier_rows']} supplier rows, {result['recipes']} recipes and {m} menu rows."
            )
            st.rerun()

        st.divider()
        st.subheader("Import real waste history")
        st.caption(
            "Minimum columns: service_date, facility, service_area, meal, food_item, waste_type, waste_kg."
        )
        wf = st.file_uploader("Waste history CSV / Excel", type=["csv", "xlsx", "xls"], key="waste")
        if wf:
            df = _read_upload(wf)
            clean, problems = validate_waste_dataframe(df)
            st.dataframe(clean.head(25), use_container_width=True, hide_index=True)
            if problems:
                for p in problems:
                    st.error(p)
            elif st.button("Import real waste records", type="primary"):
                result = import_waste_dataframe(clean, recorded_by=user["id"])
                st.success(f"Imported {result['inserted']} real waste records.")
                st.rerun()
