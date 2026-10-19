from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.db import fetchall, fetchone
from src.intake import (
    MEAL_LABELS, MISSED_REASONS, PLATE_MEALS, UNEATEN_REASONS, ComponentEntry, MealEntry,
    PLATE_MEALS as _MEALS, add_order, correct_observation, current_observation,
    day_overview, ensure_standard_orders, meal_results, menu_components_for_meal, orders_for, residents,
    update_resident_location,
    save_observation,
)
from src.resident_choices import CHOICES, MEAL_GROUPS, ensure_soup_items
from src.textures import NO_MELTING_DESSERTS, texture_label
from src.styles import page_header

PCTS = ["0%", "25%", "50%", "75%", "100%", "Not seen"]
OUTCOMES = {"served": "Ate", "refused": "Refused", "missed": "Not there"}
EDITOR_ROLES = {"admin", "dietitian"}

DEFAULT_SERVED_G = {
    "protein": 180, "carbohydrate": 120, "vegetables": 80, "soup": 250,
    "dessert": 120, "drinks": 200, "other": 120,
}

def _default_served_g(item):
    fid = item.get("food_item_id")
    if fid:
        rec = fetchone("SELECT serving_size_g FROM sponsor_recipes WHERE food_item_id=? ORDER BY id DESC LIMIT 1", (fid,))
        if rec and rec.get("serving_size_g"):
            return float(rec["serving_size_g"])
    return float(DEFAULT_SERVED_G.get(item.get("component_group"), 120))


def _default_meal():
    hour = datetime.now().hour + datetime.now().minute / 60
    for meal, until in (("Breakfast", 9.5), ("Morning Tea", 11), ("Lunch", 14), ("Afternoon Tea", 16.5)):
        if hour < until:
            return meal
    return "Dinner"


def _pct_to_values(choice):
    return ("not_observed", None) if choice == "Not seen" else ("observed", int(choice.rstrip("%")))


def _values_to_pct(status, pct):
    return f"{pct}%" if status == "observed" else "Not seen"


def _item_options(resident, service_date, meal):
    """Everything a resident can add to this meal: today's menu, Harbison soups and resident choices."""
    variant = resident["menu_variant"] or "Regular"
    options = []
    if meal in ("Breakfast", "Lunch", "Dinner"):
        options += [("Today's menu", m["item_label"], m["component_group"], m["food_item_id"])
                    for m in menu_components_for_meal(service_date, meal, variant)]
    soup_ids = ensure_soup_items()
    suffix = f" ({texture_label(variant)})" if variant in NO_MELTING_DESSERTS else ""
    options += [("Soups", name + suffix, "soup", fid) for name, fid in soup_ids.items()]
    options += [(section, name, group, None) for name, group, section, melts in CHOICES
                if not (melts and variant in NO_MELTING_DESSERTS)]
    options.append(("Other", "Other (type a name)", "other", None))
    allowed = MEAL_GROUPS.get(meal)
    return [o for o in options if o[0] in allowed] if allowed else options


def _add_item(base, resident, service_date, meal, user):
    with st.popover("+ Add item"):
        options = _item_options(resident, service_date, meal)
        groups = list(dict.fromkeys(o[0] for o in options))
        group = st.pills("Group", groups, key=f"{base}_addgroup", default=groups[0])
        if not group:
            return
        food_item_id, item_group = None, "other"
        if group == "Other":
            label = st.text_input("Item name", key=f"{base}_addname", max_chars=60)
        else:
            in_group = [o for o in options if o[0] == group]
            label = st.pills("Item", [o[1] for o in in_group], key=f"{base}_additem_{group}")
            if label:
                _, _, item_group, food_item_id = next(o for o in in_group if o[1] == label)
        if resident["menu_variant"] in NO_MELTING_DESSERTS and group == "Desserts":
            st.caption("Ice cream and jelly are hidden for this diet.")
        if st.button(f"Add {label}" if label else "Add", type="primary", key=f"{base}_addbtn",
                     disabled=not (label or "").strip()):
            add_order(resident["id"], service_date, meal, label, item_group, food_item_id, user["id"])
            st.rerun()


def _entry(user, resident, service_date, meal, items, existing=None):
    base = f"pw_{resident['id']}_{service_date.isoformat()}_{meal}_{'e' if existing else 'n'}"
    if existing:
        items = [{"item_label": c["item_label"], "component_group": c["component_group"],
                  "food_item_id": c["food_item_id"]} for c in existing["components"]] or items
        if f"{base}_out" not in st.session_state:  # first render of the edit form: prefill saved values
            st.session_state[f"{base}_out"] = existing["meal_status"] if existing["meal_status"] in OUTCOMES else "served"
            for i, comp in enumerate(existing["components"]):
                st.session_state[f"{base}_{i}"] = _values_to_pct(comp["observed_status"], comp["intake_pct"])
                st.session_state[f"{base}_{i}_g"] = float(comp.get("served_weight_g") or _default_served_g(comp))
                if comp["reason_uneaten"]:
                    st.session_state[f"{base}_{i}_why"] = comp["reason_uneaten"]
    st.session_state.setdefault(f"{base}_out", "served")

    outcome = st.segmented_control("Outcome", list(OUTCOMES), format_func=OUTCOMES.get, key=f"{base}_out",
                                   label_visibility="collapsed") or "served"
    entry = MealEntry(resident["id"], service_date, meal, outcome)
    missing = []
    if outcome == "missed":
        entry.missed_reason = st.selectbox("Why?", MISSED_REASONS, key=f"{base}_missed")
    elif outcome == "served":
        if not items:
            st.caption("Nothing ordered for this meal.")
        q1, q2, _ = st.columns([1, 1, 2])
        fill = "100%" if q1.button("All 100%", key=f"{base}_all", use_container_width=True) else None
        if q2.button("Clear", key=f"{base}_clr", use_container_width=True):
            fill = "clear"
        h1, h2, h3 = st.columns([1.25, 0.8, 2.2])
        h1.caption("Food item")
        h2.caption("Served weight")
        h3.caption("Observed intake")
        for i, it in enumerate(items):
            key = f"{base}_{i}"
            if fill == "clear":
                st.session_state.pop(key, None)
            elif fill:
                st.session_state[key] = fill
            weight_key = f"{base}_{i}_g"
            if weight_key not in st.session_state:
                st.session_state[weight_key] = _default_served_g(it)
            left, middle, right = st.columns([1.25, 0.8, 2.2], vertical_alignment="center")
            left.markdown(f"**{it['item_label']}**")
            served_g = middle.number_input(
                f"Served grams for {it['item_label']}", min_value=1.0, max_value=2000.0, step=5.0,
                key=weight_key, label_visibility="collapsed", help="Actual weight of this food served to the resident."
            )
            choice = right.segmented_control(it["item_label"], PCTS, key=key, label_visibility="collapsed")
            reason = None
            if choice in ("0%", "25%", "50%"):
                reason = right.selectbox("Reason", ["Reason (optional)"] + UNEATEN_REASONS, key=f"{key}_why",
                                         label_visibility="collapsed")
            if not choice:
                missing.append(it["item_label"])
                continue
            status, pct = _pct_to_values(choice)
            entry.components.append(ComponentEntry(
                component_group=it["component_group"], item_label=it["item_label"], observed_status=status,
                intake_pct=pct, food_item_id=it.get("food_item_id"), served_weight_g=float(served_g),
                reason_uneaten=None if reason in (None, "Reason (optional)") else reason))
        if not existing:
            _add_item(base, resident, service_date, meal, user)

    with st.expander("Note"):
        entry.staff_observation = st.text_area("Note", key=f"{base}_note", max_chars=300,
                                               label_visibility="collapsed", placeholder="Optional. No names.")
    why = st.text_input("Reason for change", key=f"{base}_why_edit", max_chars=300) if existing else ""

    ready = not missing and (outcome != "served" or entry.components) and (not existing or why.strip())
    if st.button("Save changes" if existing else "Save", type="primary", use_container_width=True,
                 key=f"{base}_save", disabled=not ready):
        try:
            if existing:
                obs_id = correct_observation(existing["id"], entry, why, user["id"])
            else:
                obs_id = save_observation(entry, user["id"])
                st.session_state["pw_advance"] = True
            for k in [k for k in st.session_state if str(k).startswith(base)]:
                del st.session_state[k]
            st.session_state["pw_flash"] = f"Saved {resident.get('display_name') or 'room ' + str(resident['room'])}."
            st.rerun()
        except (ValueError, PermissionError, FileExistsError) as exc:
            st.error(str(exc))


def _recorded(user, resident, service_date, meal, existing, items):
    if user["role"] in EDITOR_ROLES and st.toggle("Edit", key=f"pw_edit_{existing['id']}"):
        _entry(user, resident, service_date, meal, items, existing)
        return
    if existing["meal_status"] != "served":
        st.markdown(f"**{OUTCOMES.get(existing['meal_status'], existing['meal_status'])}**"
                    + (f" · {existing['missed_reason']}" if existing["missed_reason"] else ""))
    else:
        st.dataframe(pd.DataFrame([{
            "Item": c["item_label"],
            "Served (g)": round(float(c.get("served_weight_g") or 0), 1),
            "Eaten": _values_to_pct(c["observed_status"], c["intake_pct"]),
            "Estimated eaten (g)": (
                round(float(c.get("served_weight_g") or 0) * float(c["intake_pct"]) / 100, 1)
                if c["observed_status"] == "observed" and c["intake_pct"] is not None else None
            ),
            "Reason": c["reason_uneaten"] or ""} for c in existing["components"]]),
            hide_index=True, use_container_width=True)
    if existing.get("staff_observation"):
        st.markdown(f":material/sticky_note_2: **Note:** {existing['staff_observation']}")
    st.caption(f"Saved by {existing['recorded_by_name']} at {existing['recorded_at'][11:16]}"
               + (f" · edited (v{existing['version']})" if existing["version"] > 1 else ""))


def _resident_details(user, resident, areas):
    """Name, room and dining area, with an Edit button to correct the room or dining area."""
    c1, c2, c3, c4 = st.columns([2.2, 1, 2.2, 1], vertical_alignment="center")
    c1.markdown(f"<small>Resident</small><br><b style='font-size:1.25rem'>"
                f"{resident.get('display_name') or resident['resident_code']}</b>", unsafe_allow_html=True)
    c2.markdown(f"<small>Room</small><br><b style='font-size:1.25rem'>{resident['room'] or '-'}</b>",
                unsafe_allow_html=True)
    c3.markdown(f"<small>Site</small><br><b>{resident['facility']}</b><br><small>{resident['service_area']}</small>",
                unsafe_allow_html=True)
    with c4.popover("Edit", icon=":material/edit:", use_container_width=True):
        key = f"pw_move_{resident['id']}"
        room = st.text_input("Room", value=resident["room"] or "", max_chars=10, key=f"{key}_room")
        site_ids = list(dict.fromkeys(a_["facility_id"] for a_ in areas))
        site_names = {a_["facility_id"]: a_["site"] for a_ in areas}
        site_id = st.selectbox("Site", site_ids, key=f"{key}_site", format_func=site_names.get,
                               index=site_ids.index(resident["facility_id"]) if resident["facility_id"] in site_ids else 0)
        if site_id == resident["facility_id"]:
            area_id = resident["service_area_id"]
        else:  # moving site: same-named dining area there, otherwise the site's first one
            site_areas = [a_ for a_ in areas if a_["facility_id"] == site_id]
            area_id = next((a_["id"] for a_ in site_areas if a_["area"] == resident["service_area"]),
                           site_areas[0]["id"])
        changed = room.strip() != (resident["room"] or "") or area_id != resident["service_area_id"]
        if st.button("Save", type="primary", key=f"{key}_save", disabled=not changed or not room.strip()):
            try:
                warning = update_resident_location(resident["id"], room, area_id, user["id"])
                st.session_state["pw_flash"] = warning or f"Updated: Room {room.strip()}."
                if area_id != resident["service_area_id"]:
                    st.session_state["pw_site_next"] = next(a_["facility_id"] for a_ in areas if a_["id"] == area_id)
                st.session_state["pw_pick_next"] = resident["id"]
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def page():
    user = require_roles("admin", "dietitian", "care")
    page_header("RESIDENT MEAL & CONSUMPTION RECORDS", "Resident Meals", "Find a resident, review their meal details, then record how much of each item they consumed.")
    source = "fictional_demo"  # prototype: generated resident records are synthetic test data
    if flash := st.session_state.pop("pw_flash", None):
        st.toast(flash)

    sites = fetchall("SELECT id, name FROM facilities WHERE active=1 ORDER BY name")
    areas = fetchall("""SELECT sa.id, sa.facility_id, f.name site, sa.name area, f.name || ' · ' || sa.name label
                        FROM service_areas sa
                        JOIN facilities f ON f.id=sa.facility_id WHERE sa.active=1 ORDER BY f.name, sa.name""")
    if (moved_site := st.session_state.pop("pw_site_next", None)) is not None:
        st.session_state["pw_site"] = moved_site
    if sites and st.session_state.get("pw_site") not in [s_["id"] for s_ in sites]:
        st.session_state["pw_site"] = sites[0]["id"]
    c1, c2 = st.columns(2)
    service_date = c1.date_input("Date", date.today(), max_value=date.today(), key="pw_date")
    site = c2.selectbox("Site", [s_["id"] for s_ in sites], key="pw_site",
                        format_func=lambda i: next(s_["name"] for s_ in sites if s_["id"] == i))

    source_counts = {
        "Real data": fetchone("SELECT COUNT(*) n FROM intake_residents WHERE data_source='real' AND active=1 AND facility_id=?", (site,))["n"],
        "Synthetic data": fetchone("SELECT COUNT(*) n FROM intake_residents WHERE data_source='fictional_demo' AND active=1 AND facility_id=?", (site,))["n"],
    }
    source_options = [label for label, count in source_counts.items() if count]
    if not source_options:
        source_options = ["Real data"]
    if len(source_options) == 1:
        source_label = source_options[0]
        st.caption(f"Resident data source: {source_label}")
    else:
        source_label = st.selectbox("Resident data source", source_options, key="pw_source")
    source = "real" if source_label == "Real data" else "fictional_demo"

    view = st.segmented_control("View", ["Record", "All orders"], default="Record", key="pw_view",
                                label_visibility="collapsed") or "Record"

    if view == "All orders":
        everyone = residents(source, facility_id=site)
        for m in _MEALS:
            ensure_standard_orders(everyone, service_date, m)
        overview = day_overview(source, service_date, facility_id=site)
        if overview.empty:
            st.caption("No residents.")
        else:
            st.dataframe(overview, hide_index=True, use_container_width=True, height=min(38 * len(overview) + 40, 700))
        return

    st.session_state.setdefault("pw_meal", _default_meal())
    meal = st.segmented_control("Meal", PLATE_MEALS, key="pw_meal", format_func=MEAL_LABELS.get,
                                label_visibility="collapsed") or "Lunch"
    people = residents(source, facility_id=site)
    if not people:
        st.info("No residents at this site yet. Add them in Import residents.")
        return
    ensure_standard_orders(people, service_date, meal)
    orders = orders_for(source, service_date, meal)
    results = meal_results(source, service_date, meal)
    ids = [p["id"] for p in people]
    pending = [i for i in ids if i not in results]
    if (keep := st.session_state.pop("pw_pick_next", None)) in ids:
        st.session_state["pw_resident"] = keep
    if st.session_state.pop("pw_advance", False) or st.session_state.get("pw_resident") not in ids:
        st.session_state["pw_resident"] = pending[0] if pending else ids[0]
    done = len(ids) - len(pending)
    st.progress(done / len(ids), text=f"{MEAL_LABELS[meal]}: {done} / {len(ids)} done")

    by_id = {p["id"]: p for p in people}
    st.selectbox("Find resident", ids, key="pw_resident",
                 format_func=lambda i: f"{'✓ ' if i in results else ''}Room {by_id[i]['room']}")
    resident = next(p for p in people if p["id"] == st.session_state["pw_resident"])
    items = orders.get(resident["id"], [])

    with st.container(border=True):
        _resident_details(user, resident, areas)
        existing = current_observation(resident["id"], service_date, meal)
        if existing:
            _recorded(user, resident, service_date, meal, existing, items)
        else:
            _entry(user, resident, service_date, meal, items)
