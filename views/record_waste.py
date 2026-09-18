from datetime import date, datetime
import streamlit as st
from src.auth import require_roles
from src.styles import page_header, render_source_badges
from src.db import fetchall, fetchone, execute, setting, log_action
from src.menu import menu_week, menu_variants, menu_services, menu_components, menu_items
from src.costing import food_cost_per_kg
from .common import money, fmt_pct


def pct(n, d):
    return None if d is None or d <= 0 else n / d * 100


def page():
    user = require_roles("admin", "manager", "kitchen")
    page_header(
        "KITCHEN OPERATIONS",
        "Record Food Waste",
        "Select the service date and real Autumn/Winter menu first. A location is required only when saving the record.",
    )
    render_source_badges([("Real Harbison menu", "source-green"), ("No synthetic menu items", "source-blue")])

    st.subheader("1. Menu selection")
    a, b = st.columns(2)
    service_date = a.date_input("Service date", date.today())
    variants = menu_variants(service_date)
    if not variants:
        st.warning("No imported menu schedule is available for this date.")
        return
    default_variant = variants.index("Regular") if "Regular" in variants else 0
    variant = b.selectbox("Menu type", variants, index=default_variant)

    services = menu_services(service_date, variant)
    if not services:
        st.warning("No meal services are available for this date/menu type.")
        return
    c, d = st.columns(2)
    meal = c.selectbox("Meal service", services)
    components = menu_components(service_date, variant, meal)
    comp = d.selectbox("Menu component", ["All components"] + components)
    items = menu_items(service_date, meal, variant, comp)
    st.caption(
        f"Menu cycle: Week {menu_week(service_date)} | {service_date.strftime('%A')} | {variant} | {meal}"
    )
    if not items:
        st.warning("No menu items found for this selection.")
        return

    labels = [f"{x['name']} | {x['component']}" for x in items]
    label = st.selectbox("Food item", labels)
    item = items[labels.index(label)]
    if item.get("linked_recipe_food_item_id"):
        st.caption(f"Linked costing recipe: {item['linked_recipe_name']}")

    st.subheader("2. Location")
    facilities = fetchall("SELECT * FROM facilities WHERE active=1 ORDER BY name")
    fid = None
    aid = None
    if not facilities:
        st.warning(
            "No real facility/service-area names are configured yet. You can still review the menu and waste form, but saving is disabled until a location is added in Menu & Locations."
        )
    else:
        e, f = st.columns(2)
        fac = e.selectbox("Facility", [x["name"] for x in facilities])
        fid = next(x["id"] for x in facilities if x["name"] == fac)
        areas = fetchall(
            "SELECT * FROM service_areas WHERE facility_id=? AND active=1 ORDER BY name", (fid,)
        )
        if areas:
            area = f.selectbox("Service area", [x["name"] for x in areas])
            aid = next(x["id"] for x in areas if x["name"] == area)
        else:
            f.warning("Add a service area for this facility before saving.")

    meal_row = fetchone("SELECT id FROM meals WHERE name=?", (meal,))
    mid = meal_row["id"] if meal_row else execute(
        "INSERT INTO meals(name,sort_order) VALUES(?,99)", (meal,)
    )

    st.subheader("3. Waste details")
    waste_type = st.radio("Waste type", ["Production Waste", "Plate Waste"], horizontal=True)
    q1, q2, q3 = st.columns(3)
    prepared = q1.number_input(
        "Prepared kg", min_value=0.0, value=0.0, step=.1,
        help="Used for production-waste percentage when measured."
    )
    served = q2.number_input(
        "Served kg", min_value=0.0, value=0.0, step=.1,
        help="Used for plate-waste percentage when measured."
    )
    waste = q3.number_input("Waste kg", min_value=0.0, value=0.0, step=.1)
    residents = st.number_input("Residents / meals served (optional)", min_value=0, value=0, step=1)
    notes = st.text_area("Notes (optional)", max_chars=300)

    prep = prepared or None
    srv = served or None
    wp = pct(waste, prep if waste_type == "Production Waste" else srv)
    cost_food_item_id = item.get("linked_recipe_food_item_id") or item["id"]
    cost, cost_source = food_cost_per_kg(cost_food_item_id, service_date)
    waste_cost = waste * cost if cost is not None else None
    kpi = float(setting("plate_waste_kpi", "20") or 20)

    st.subheader("4. Review")
    r1, r2, r3 = st.columns(3)
    r1.metric("Waste", f"{waste:.2f} kg")
    r2.metric("Waste %", fmt_pct(wp))
    r3.metric("Estimated cost", money(waste_cost), help=cost_source)
    if cost is None:
        st.caption("Cost will appear when the linked recipe has enough confirmed ingredient prices.")

    errs = []
    if waste_type == "Production Waste" and prep is not None and waste > prep:
        errs.append("Production waste cannot exceed prepared weight.")
    if waste_type == "Plate Waste" and srv is not None and waste > srv:
        errs.append("Plate waste cannot exceed served weight.")
    for err in errs:
        st.error(err)
    if waste_type == "Plate Waste" and wp is not None and wp > kpi:
        st.warning(f"Plate waste is above the configured {kpi:.1f}% KPI.")

    location_ready = fid is not None and aid is not None
    if not location_ready:
        st.caption("Saving is disabled until a real facility and service area are configured.")

    if st.button(
        "Save real waste record",
        type="primary",
        use_container_width=True,
        disabled=waste <= 0 or bool(errs) or not location_ready,
    ):
        execute(
            """INSERT INTO transactions(
                created_at,service_date,facility_id,service_area_id,meal_id,food_item_id,
                waste_type,prepared_kg,served_kg,waste_kg,waste_percentage,
                cost_per_kg_snapshot,waste_cost,resident_count,notes,recorded_by,is_demo,
                menu_variant,menu_component)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
            (
                datetime.now().isoformat(timespec="seconds"), service_date.isoformat(),
                fid, aid, mid, item["id"], waste_type, prep, srv, waste, wp, cost,
                waste_cost, residents or None, notes.strip() or None, user["id"],
                variant, item["component"],
            ),
        )
        log_action(user["id"], "CREATE_WASTE_RECORD", f"{item['name']} {waste:.2f}kg")
        st.success("Real waste record saved.")
