# Harbison Food Waste Prototype — V6.1 Synthetic Realism Hotfix

This patch improves the synthetic ML dataset used for prototype analysis and forecasting.

## Changes
- Adds slow occupancy drift, weekly/daily demand shocks and occasional unusual service days.
- Adds changing food preference/acceptance instead of fixed item popularity.
- Separates preparation planning from realised demand so preparation is not a near-perfect formula.
- Keeps the four-week Harbison menu as the authoritative schedule structure.
- Skips generic `Harbison Morning Tea` / `Harbison Afternoon Tea` service headings as item-level ML targets.
- Keeps all generated records explicitly marked synthetic.
- Dashboard/report item rankings exclude generic service headings.
- Reports distinguish facility + service area instead of merging same-named synthetic areas.
- Forecasting headline metrics now emphasise MAE, baseline improvement and WAPE; preparation R² remains available under Model diagnostics.

## Refresh data after copying the patch

```powershell
python generate_ml_data.py --start 2026-03-01 --end 2026-09-30 --seed 42
python -m streamlit run app.py
```

The generator replaces the previous synthetic ML run by default. Real Harbison records are not deleted.
