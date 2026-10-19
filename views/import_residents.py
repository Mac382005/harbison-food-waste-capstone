import pandas as pd
import streamlit as st

from src.auth import require_roles
from src.db import fetchall
from src.intake import residents
from src.resident_import import apply, preview, read_file, template_csv
from src.styles import page_header
from src.textures import texture_label

SOURCE = "real"
ACTION_ORDER = ["Error", "New", "Update", "Discharge", "Re-admit", "Remove (not in file)", "No change",
                "Skip (discharged, not on file)"]


def _site_names() -> dict[int, str]:
    return {s["id"]: s["name"] for s in fetchall("SELECT id, name FROM facilities WHERE active=1 ORDER BY name")}


def page():
    user = require_roles("admin")
    page_header("RESIDENT MEAL & CONSUMPTION RECORDS", "Import residents",
                "Upload or update a site's resident list. Locations are managed centrally in Food Waste Management.")
    _upload(user)


def _upload(user):
    names = _site_names()
    if not names:
        st.info("No sites are configured yet. Add the facility and dining areas in **Food Waste Management → Menu & Locations** first.")
        return

    st.markdown("##### 1. Choose the site")
    if (new_site := st.session_state.pop("ip_site_next", None)) is not None:
        st.session_state["ip_site"] = new_site
    if st.session_state.get("ip_site") not in names:
        st.session_state["ip_site"] = next(iter(names))
    site = st.selectbox("Site", list(names), key="ip_site", format_func=names.get, label_visibility="collapsed")
    site_name = names[site]
    areas = [a["name"] for a in fetchall(
        "SELECT name FROM service_areas WHERE facility_id=? AND active=1 ORDER BY name", (site,))]
    if areas:
        st.caption(f"Dining areas at {site_name}: {', '.join(areas)}. Use these names in the Dining area column.")
    else:
        st.warning(f"{site_name} has no dining areas yet. Add them in **Food Waste Management → Menu & Locations** first.")

    st.markdown("##### 2. Download and complete the resident template")
    st.download_button(
        "Download resident template",
        template_csv(),
        "harbison_residents_template.csv",
        "text/csv",
        width="stretch",
    )
    st.caption(
        "Required columns: Resident ID, Name, Room and Dining area. "
        "Diet may be Regular, Soft & Bite-Sized, Minced & Moist or Pureed. "
        "Status may be Active or Discharged. The dining-area name must match the selected site exactly."
    )

    st.markdown(f"##### 3. Upload the list for {site_name}")
    upload = st.file_uploader(f"Resident list for {site_name} (CSV or Excel)", type=["csv", "xlsx", "xls"],
                              key=f"ip_file_{site}", label_visibility="collapsed")

    if upload is not None:
        try:
            plan = preview(read_file(upload), SOURCE, facility_id=site)
        except ValueError as exc:
            st.error(str(exc))
            plan = None
        if plan is not None and not plan.empty:
            counts = plan.Action.value_counts()
            ready = int(counts.drop(labels=["Error", "No change", "Skip (discharged, not on file)"],
                                    errors="ignore").sum())
            cols = st.columns(5)
            labels = {"Error": "Problems", "Remove (not in file)": "Removed", "Discharge": "Discharged"}
            for col, name in zip(cols, ["New", "Update", "Discharge", "Remove (not in file)", "Error"]):
                col.metric(labels.get(name, name), int(counts.get(name, 0)))
            shown = plan.drop(columns=[c for c in plan.columns if c.startswith("_")])
            shown["order"] = shown.Action.map({a_: i for i, a_ in enumerate(ACTION_ORDER)})
            st.dataframe(shown.sort_values(["order", "Row"]).drop(columns="order"), hide_index=True,
                         use_container_width=True)
            removing = int(counts.get("Remove (not in file)", 0))
            usable = int((plan.Action != "Error").sum()) - removing
            confirmed = True
            if usable == 0:
                st.error(f"None of the rows in this file can be imported for {site_name}, so nothing will change. "
                         "Check you chose the right site and fix the problems listed.")
            elif removing:
                st.warning(f"{removing} resident(s) at {site_name} are not in this file and will be removed from "
                           "Resident Meals. Their past meal records are kept. Other sites are not changed.")
                confirmed = st.checkbox(f"Yes, remove these {removing} resident(s) from Resident Meals",
                                        key=f"ip_confirm_{site}")
            if counts.get("Error", 0) and usable:
                st.warning("Rows with problems will be skipped. Fix them in the file and upload again.")
            if st.button("Import", type="primary", disabled=ready == 0 or usable == 0 or not confirmed):
                done = apply(plan, SOURCE, user["id"])
                st.session_state["ip_done"] = done
                st.session_state.pop(f"ip_file_{site}", None)
                st.rerun()

    if done := st.session_state.pop("ip_done", None):
        st.success(f"Imported: {done['New']} new, {done['Update']} updated, {done['Discharge']} discharged, "
                   f"{done['Re-admit']} re-admitted, {done['Remove (not in file)']} removed. "
                   "Resident Meals now shows this list.")

    st.divider()
    with st.expander(f"Current residents at {site_name}"):
        people = residents(SOURCE, facility_id=site, active_only=False)
        if people:
            df = pd.DataFrame(people)
            df["Status"] = df.active.map({1: "Active", 0: "Discharged"})
            df["menu_variant"] = df.menu_variant.map(texture_label)
            st.dataframe(df[["resident_code", "display_name", "room", "facility", "service_area", "menu_variant",
                             "Status"]].rename(columns={
                "resident_code": "Resident ID", "display_name": "Name", "room": "Room", "facility": "Facility",
                "service_area": "Dining area", "menu_variant": "Diet"}),
                hide_index=True, use_container_width=True)
        else:
            st.caption("None yet.")
