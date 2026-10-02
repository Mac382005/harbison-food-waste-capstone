# Harbison Food Waste Prototype — V6 ML Update

This update adds a reproducible synthetic-data and machine-learning workflow while keeping synthetic observations separate from real Harbison records.

## What changed

- New **Synthetic ML Data** page for managers/admins.
- Synthetic records are generated from the imported Harbison four-week menu by date, menu type, meal service, component and food item.
- The generator creates repeatable variation in resident demand, preparation quantity, production waste and plate waste using a configurable random seed.
- Synthetic records are always marked with `is_demo=1` and a `synthetic_run_id`.
- Real records remain `is_demo=0` and are never overwritten by the synthetic generator.
- Dashboard and Reports can switch between **Synthetic ML data**, **Real Harbison data**, and **Real + synthetic** when both exist.
- Forecasting now trains two ML models:
  - preparation quantity (`prepared_kg`)
  - expected plate-waste percentage (meal-quality signal)
- Evaluation uses a **time-based holdout**, not a random train/test split.
- The ML pipeline uses target encoding for high-cardinality categorical fields and a histogram gradient-boosting regressor.
- Forecast inputs use the actual scheduled Harbison menu for the selected date.

## Synthetic-data assumptions

The generator is intended for prototype development and demonstration only. It does not claim to reproduce measured Harbison outcomes.

It uses:

- the real imported Harbison menu schedule;
- confirmed recipe serving sizes where available;
- simulated resident counts and menu-type proportions;
- stable food-preference effects plus random day-to-day variation;
- preparation buffers and production-waste variation;
- menu/category/texture effects for simulated plate waste.

The supplier comparison is **not** treated as historical ordering data because the supplied comparison file is not a transaction/order history. Confirmed food costs are used only when they already exist in the prototype.

## Recommended development dataset

```powershell
python generate_ml_data.py --start 2026-03-01 --end 2026-09-30 --seed 42
```

With two simulated sites and two dining areas (used only if no locations are configured), this normally creates tens of thousands of transactions, sufficient for the prototype ML workflow.

## Install / migrate

```powershell
pip install -r requirements.txt
python migrate_to_v6_ml.py
python generate_ml_data.py --start 2026-03-01 --end 2026-09-30 --seed 42
python -m streamlit run app.py
```

## Reporting rule

When presenting results, describe synthetic results as **simulated/model-development results**, not as measured Harbison waste performance. Real and synthetic sources can always be selected separately in the UI.
