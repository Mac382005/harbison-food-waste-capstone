from __future__ import annotations

import pandas as pd
from .db import connection


def transactions_df():
    q = """
    SELECT t.id,t.created_at,t.service_date,f.name facility,sa.name service_area,m.name meal,
           fi.name food_item,fc.name category,t.waste_type,t.prepared_kg,t.served_kg,
           t.waste_kg,t.waste_percentage,t.cost_per_kg_snapshot,t.waste_cost,
           t.waste_reason,t.resident_count,t.notes,t.is_demo,
           COALESCE(u.display_name,'System/Demo') recorded_by
    FROM transactions t
    JOIN facilities f ON f.id=t.facility_id
    JOIN service_areas sa ON sa.id=t.service_area_id
    JOIN meals m ON m.id=t.meal_id
    JOIN food_items fi ON fi.id=t.food_item_id
    LEFT JOIN food_categories fc ON fc.id=fi.category_id
    LEFT JOIN users u ON u.id=t.recorded_by
    ORDER BY t.service_date DESC,t.id DESC
    """
    with connection() as c:
        df = pd.read_sql_query(q, c)
    if not df.empty:
        df["service_date"] = pd.to_datetime(df["service_date"])
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def filtered(df, facility="All", area="All", meal="All", waste_type="All", food="All", start=None, end=None):
    out = df.copy()
    if out.empty:
        return out
    if start:
        out = out[out.service_date.dt.date >= start]
    if end:
        out = out[out.service_date.dt.date <= end]
    for col, val in [("facility",facility),("service_area",area),("meal",meal),("waste_type",waste_type),("food_item",food)]:
        if val != "All":
            out = out[out[col] == val]
    return out
