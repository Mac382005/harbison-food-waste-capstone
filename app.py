import streamlit as st

from src.db import init_db
from src.seed import seed_all
from src.auth import current_user, login_screen, logout, ROLE_LABELS
from src.styles import apply_styles

from views import dashboard, record_waste, transactions, reports, forecasting_page, ingredients, recipes, reference, users, admin

st.set_page_config(page_title="Harbison Food Waste Intelligence", page_icon="🍽️", layout="wide")
apply_styles()
init_db()
seed_all()

user=current_user()
if not user:
    login_screen()
    st.stop()

with st.sidebar:
    st.markdown("### 🍽️ Harbison Food Waste")
    st.caption(f"{user['display_name']}")
    st.caption(ROLE_LABELS.get(user["role"],user["role"]))
    if st.button("Sign out",use_container_width=True):
        logout()

role=user["role"]

operations=[]
analytics=[]
configuration=[]

if role in {"admin","manager","kitchen"}:
    operations.append(st.Page(record_waste.page,title="Record Waste",icon=":material/scale:",url_path="record-waste"))
if role in {"admin","manager","kitchen","dietitian"}:
    operations.append(st.Page(transactions.page,title="Transactions",icon=":material/receipt_long:",url_path="transactions"))

if role in {"admin","manager","dietitian"}:
    analytics += [
        st.Page(dashboard.page,title="Dashboard",icon=":material/dashboard:",url_path="dashboard",default=True),
        st.Page(reports.page,title="Reports",icon=":material/bar_chart:",url_path="reports"),
        st.Page(forecasting_page.page,title="Forecasting",icon=":material/trending_up:",url_path="forecasting"),
    ]

if role in {"admin","manager"}:
    configuration += [
        st.Page(ingredients.page,title="Ingredients & Prices",icon=":material/payments:",url_path="ingredients-prices"),
        st.Page(recipes.page,title="Recipes & Costing",icon=":material/menu_book:",url_path="recipes-costing"),
        st.Page(reference.page,title="Menu & Locations",icon=":material/settings:",url_path="menu-locations"),
    ]

if role=="admin":
    configuration += [
        st.Page(users.page,title="Users & Access",icon=":material/admin_panel_settings:",url_path="users-access"),
        st.Page(admin.page,title="System Admin",icon=":material/tune:",url_path="system-admin"),
    ]

sections={}
if analytics: sections["Analytics"]=analytics
if operations: sections["Operations"]=operations
if configuration: sections["Configuration"]=configuration

pg=st.navigation(sections)
pg.run()
