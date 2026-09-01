from __future__ import annotations
import math
import streamlit as st


def money(v):
    return "N/A" if v is None or (isinstance(v,float) and math.isnan(v)) else f"A${v:,.2f}"


def fmt_pct(v):
    return "N/A" if v is None or (isinstance(v,float) and math.isnan(v)) else f"{v:.1f}%"


def role_banner(user):
    labels = {
        "admin":"System Administrator",
        "manager":"Foodservice Manager",
        "kitchen":"Kitchen Staff",
        "dietitian":"Dietitian / Analyst",
    }
    st.markdown(
        f'<span class="role-chip">Signed in as {user["display_name"]} · {labels.get(user["role"],user["role"])}</span>',
        unsafe_allow_html=True,
    )
