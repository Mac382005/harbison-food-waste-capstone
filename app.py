import streamlit as st

from src.db import init_db
from src.seed import seed_core
from src.auth import current_user, login_screen, logout, ROLE_LABELS
from src.styles import apply_styles
from src.sponsor_import import ensure_sponsor_data_loaded
from src.menu_import import ensure_menu_loaded

from views import (
    dashboard,
    record_waste,
    transactions,
    reports,
    forecasting_page,
    ingredients,
    recipes,
    reference,
    sponsor_data,
    synthetic_ml,
    users,
    admin,
    plate_waste,
    import_residents,
    reasons_notes,
)

st.set_page_config(
    page_title="Harbison Food Waste Intelligence",
    page_icon="🍽️",
    layout="wide",
)

apply_styles()
init_db()
seed_core()
ensure_sponsor_data_loaded()
ensure_menu_loaded()

PROGRAMS = {
    "waste": {
        "title": "Food Waste Management",
        "subtitle": "Waste records, costing, reports and forecasting.",
        "icon": ":material/delete:",
        "roles": {"admin", "manager", "kitchen", "dietitian"},
    },
    "plate": {
        "title": "Resident Meal & Consumption Records",
        "subtitle": "Resident details, meal orders, intake and consumption records.",
        "icon": ":material/restaurant:",
        "roles": {"admin", "dietitian", "care"},
    },
}


def choose_program():
    st.markdown(
        """<div class="hero"><div class="hero-kicker">HARBISON CARE · CAPSTONE PROTOTYPE</div>
        <div class="hero-title">Choose a program</div></div>""",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for col, (key, prog) in zip(cols, PROGRAMS.items()):
        with col.container(border=True):
            st.markdown(f"## {prog['title']}")
            st.caption(prog["subtitle"])
            if st.button("Open", key=f"open_{key}", type="primary", icon=prog["icon"], use_container_width=True):
                st.session_state["program"] = key
                st.rerun()


program = st.session_state.get("program")
if program not in PROGRAMS:
    choose_program()
    st.stop()
prog = PROGRAMS[program]

user = current_user()
if not user:
    login_screen(prog["title"], prog["subtitle"], prog["roles"])
    _, mid, _ = st.columns([1, 1.2, 1])
    if mid.button("← Choose another program", key="back_to_programs", use_container_width=True):
        st.session_state.pop("program", None)
        st.rerun()
    st.stop()
if user["role"] not in prog["roles"]:
    st.error(f"This account can't open {prog['title']}.")
    if st.button("Choose another program"):
        st.session_state.pop("program", None)
        st.rerun()
    st.stop()

with st.sidebar:
    st.markdown(f"### {prog['title']}")
    st.caption(f"Signed in as **{user['display_name']}** · {ROLE_LABELS.get(user['role'], user['role'])}")
    if st.button("Switch program", use_container_width=True, icon=":material/swap_horiz:"):
        st.session_state.pop("program", None)
        st.rerun()
    if st.button("Sign out", use_container_width=True):
        logout()

if program == "plate":
    plate_pages = [st.Page(plate_waste.page, title="Resident Meals", icon=":material/restaurant:",
                           url_path="resident-meals", default=True)]
    if user["role"] in {"admin", "dietitian"}:
        plate_pages.append(st.Page(reasons_notes.page, title="Reasons & notes", icon=":material/sticky_note_2:",
                                   url_path="reasons-notes"))
    if user["role"] == "admin":
        plate_pages.append(st.Page(import_residents.page, title="Import residents", icon=":material/upload_file:",
                                   url_path="import-residents"))
    st.navigation(plate_pages).run()
    st.stop()

role = user["role"]
operations = []
analytics = []
configuration = []

if role in {"admin", "manager", "kitchen"}:
    operations.append(
        st.Page(
            record_waste.page,
            title="Record Waste",
            icon=":material/scale:",
            url_path="record-waste",
            default=(role == "kitchen"),
        )
    )
if role in {"admin", "manager", "kitchen", "dietitian"}:
    operations.append(
        st.Page(
            transactions.page,
            title="Transactions",
            icon=":material/receipt_long:",
            url_path="transactions",
        )
    )

if role in {"admin", "manager", "dietitian"}:
    analytics += [
        st.Page(
            dashboard.page,
            title="Dashboard",
            icon=":material/dashboard:",
            url_path="dashboard",
            default=True,
        ),
        st.Page(
            reports.page,
            title="Reports",
            icon=":material/bar_chart:",
            url_path="reports",
        ),
        st.Page(
            forecasting_page.page,
            title="Forecasting",
            icon=":material/trending_up:",
            url_path="forecasting",
        ),
    ]
    if role in {"admin", "manager"}:
        analytics.append(
            st.Page(
                synthetic_ml.page,
                title="Synthetic Data",
                icon=":material/science:",
                url_path="synthetic-ml-data",
            )
        )

if role in {"admin", "manager"}:
    configuration += [
        st.Page(
            sponsor_data.page,
            title="Harbison Data",
            icon=":material/database:",
            url_path="sponsor-data",
        ),
        st.Page(
            ingredients.page,
            title="Ingredients & Prices",
            icon=":material/payments:",
            url_path="ingredients-prices",
        ),
        st.Page(
            recipes.page,
            title="Recipes & Costing",
            icon=":material/menu_book:",
            url_path="recipes-costing",
        ),
        st.Page(
            reference.page,
            title="Menu & Locations",
            icon=":material/settings:",
            url_path="menu-locations",
        ),
    ]

if role == "admin":
    configuration += [
        st.Page(
            users.page,
            title="Users & Access",
            icon=":material/admin_panel_settings:",
            url_path="users-access",
        ),
        st.Page(
            admin.page,
            title="System Admin",
            icon=":material/tune:",
            url_path="system-admin",
        ),
    ]

sections = {}
if analytics:
    sections["Analytics"] = analytics
if operations:
    sections["Operations"] = operations
if configuration:
    sections["Configuration"] = configuration

pg = st.navigation(sections, expanded=True)
pg.run()
