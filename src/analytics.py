from __future__ import annotations

import pandas as pd
from .db import connection


def transactions_df(include_demo: bool = False, source: str | None = None):
    """Load transaction data with an explicit source mode.

    source options:
      - "real": real operational food-waste records only
      - "synthetic": menu-aligned synthetic food-waste records only

    Resident meal-consumption records remain in their own resident module and are not converted
    into weighed food-waste transactions.

    The older include_demo argument is retained for compatibility with existing pages.
    """
    if source == "synthetic":
        where = "WHERE t.synthetic_run_id IS NOT NULL"
    elif source == "real":
        where = "WHERE t.is_demo=0 AND t.synthetic_run_id IS NULL AND t.intake_observation_id IS NULL"
    else:
        where = "" if include_demo else "WHERE t.is_demo=0 AND t.synthetic_run_id IS NULL AND t.intake_observation_id IS NULL"


    q = f"""
    SELECT t.id,t.created_at,t.service_date,f.name facility,sa.name service_area,m.name meal,
           fi.name food_item,fc.name category,t.waste_type,t.prepared_kg,t.served_kg,
           t.waste_kg,t.waste_percentage,t.cost_per_kg_snapshot,t.waste_cost,
           t.waste_reason,t.resident_count,t.notes,t.is_demo,t.menu_variant,t.menu_component,
           t.synthetic_run_id,t.intake_observation_id,
           CASE WHEN t.synthetic_run_id IS NOT NULL THEN 'Synthetic'
                WHEN t.is_demo=0 THEN 'Real'
                ELSE 'Legacy demo' END data_source,
           COALESCE(u.display_name,'System') recorded_by
    FROM transactions t
    JOIN facilities f ON f.id=t.facility_id
    JOIN service_areas sa ON sa.id=t.service_area_id
    JOIN meals m ON m.id=t.meal_id
    JOIN food_items fi ON fi.id=t.food_item_id
    LEFT JOIN food_categories fc ON fc.id=fi.category_id
    LEFT JOIN users u ON u.id=t.recorded_by
    {where}
    ORDER BY t.service_date DESC,t.id DESC
    """
    with connection() as c:
        df = pd.read_sql_query(q, c)
    if not df.empty:
        df["service_date"] = pd.to_datetime(df["service_date"])
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def filtered(df, facility="All", area="All", meal="All", waste_type="All", food="All", start=None, end=None, menu_variant="All"):
    out = df.copy()
    if out.empty:
        return out
    if start:
        out = out[out.service_date.dt.date >= start]
    if end:
        out = out[out.service_date.dt.date <= end]
    for col, val in [
        ("facility", facility),
        ("service_area", area),
        ("meal", meal),
        ("waste_type", waste_type),
        ("food_item", food),
        ("menu_variant", menu_variant),
    ]:
        if val != "All" and col in out.columns:
            out = out[out[col] == val]
    return out


SOURCE_MODES = {
    "Synthetic data": "synthetic",
    "Real data": "real",
}


def available_sources() -> list[str]:
    """Only two analysis modes are exposed: synthetic or real."""
    with connection() as c:
        syn = c.execute("SELECT COUNT(*) FROM transactions WHERE synthetic_run_id IS NOT NULL").fetchone()[0]
        real = c.execute(
            "SELECT COUNT(*) FROM transactions WHERE is_demo=0 AND synthetic_run_id IS NULL AND intake_observation_id IS NULL"
        ).fetchone()[0]
    opts = []
    if syn:
        opts.append("Synthetic data")
    if real:
        opts.append("Real data")
    return opts
