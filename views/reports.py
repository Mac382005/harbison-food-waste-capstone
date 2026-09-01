import streamlit as st
import plotly.express as px

from src.auth import require_roles
from src.styles import page_header
from src.analytics import transactions_df, filtered
from src.db import setting
from .common import money, fmt_pct


def page():
    require_roles("admin","manager","dietitian")
    page_header("MANAGEMENT", "Reports", "Daily, weekly and four-week-cycle views for operations, meal quality and cost.")

    df=transactions_df()
    if df.empty:
        st.info("No data available.")
        return

    c1,c2,c3,c4=st.columns(4)
    facility=c1.selectbox("Facility",["All"]+sorted(df.facility.unique().tolist()))
    area=c2.selectbox("Service area",["All"]+sorted(df.service_area.unique().tolist()))
    meal=c3.selectbox("Meal",["All"]+sorted(df.meal.unique().tolist()))
    wtype=c4.selectbox("Waste type",["All","Production Waste","Plate Waste"])
    period=st.segmented_control("Report grouping",["Daily","Weekly","4-week"],default="Weekly")
    fdf=filtered(df,facility=facility,area=area,meal=meal,waste_type=wtype)

    kpi=float(setting("plate_waste_kpi","20") or 20)
    plate=fdf[fdf.waste_type=="Plate Waste"]
    breaches=int((plate.waste_percentage.fillna(-1)>kpi).sum()) if not plate.empty else 0

    a,b,c,d=st.columns(4)
    a.metric("Waste",f"{fdf.waste_kg.sum():.1f} kg")
    b.metric("Waste cost",money(fdf.waste_cost.fillna(0).sum()))
    c.metric("Avg plate waste",fmt_pct(plate.waste_percentage.dropna().mean() if not plate.empty else None))
    d.metric("KPI breaches",breaches)

    if fdf.empty:
        return

    temp=fdf.copy()
    if period=="Daily":
        temp["period"]=temp.service_date.dt.date.astype(str)
    elif period=="Weekly":
        temp["period"]=temp.service_date.dt.to_period("W").astype(str)
    else:
        origin=temp.service_date.min()
        temp["period_index"]=((temp.service_date-origin).dt.days//28)+1
        temp["period"]="Cycle "+temp["period_index"].astype(str)

    trend=temp.groupby(["period","waste_type"],as_index=False).waste_kg.sum()
    st.plotly_chart(px.bar(trend,x="period",y="waste_kg",color="waste_type",barmode="group",title=f"{period} waste"),use_container_width=True)

    left,right=st.columns(2)
    by_area=fdf.groupby(["service_area","waste_type"],as_index=False).waste_kg.sum()
    left.plotly_chart(px.bar(by_area,x="service_area",y="waste_kg",color="waste_type",title="Waste by service area"),use_container_width=True)

    if not plate.empty:
        quality=plate.dropna(subset=["waste_percentage"]).groupby("food_item",as_index=False).agg(
            avg_plate_waste=("waste_percentage","mean"),
            observations=("id","count")
        ).sort_values("avg_plate_waste",ascending=False)
        quality["status"]=quality.avg_plate_waste.apply(lambda x:"Above KPI" if x>kpi else "Within KPI")
        right.plotly_chart(px.bar(quality.head(12),x="avg_plate_waste",y="food_item",orientation="h",color="status",title="Meal-quality signals"),use_container_width=True)

    st.download_button("Export report CSV",fdf.to_csv(index=False).encode(),"food_waste_report.csv","text/csv")
