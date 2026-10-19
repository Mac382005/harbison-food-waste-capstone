# Harbison Food Waste Intelligence - V6 ML

A Streamlit + SQLite prototype for recording, analysing and forecasting food waste in residential aged care using Harbison reference data.

## Data currently used

- Autumn/Winter 2026 four-week menu
- Regular, Soft Bite Sized, Minced and Puree menu variants
- 12 Harbison soup recipes
- 2 selected dessert recipes with sufficiently clear serving/yield data
- Harbison supplier comparison (288 products) for reference charts and comparison only
- manual confirmed ingredient prices for recipe costing
- real waste records entered/imported when available
- clearly-labelled synthetic ML records generated from the real menu structure for model development

## Synthetic ML workflow

The V6 generator creates a reproducible training dataset from the imported Harbison menu. It simulates resident demand, preparation quantity, production waste and plate waste while preserving the real menu week/day/meal/component/menu-type structure.

Synthetic records are always separated from real operational records using `is_demo=1` and `synthetic_run_id`. Dashboard, Reports and Forecasting allow the user to select the data source explicitly.

The supplier comparison is **not** treated as historical ordering data because it is a price/reference comparison rather than an order transaction history.

## ML forecasting

Forecasting now includes two models:

- preparation quantity forecast (`prepared_kg`)
- expected plate-waste percentage / meal-quality signal

The models use menu item, category, meal, location, menu type, component, resident count and calendar context. Model evaluation uses a time-based holdout rather than a random split.

## Supplier scope

Supplier comparison remains available because it is useful reference data and supports comparison charts. The app does **not** recommend a supplier, automatically match supplier products to recipes, or automatically apply supplier quotes to costing.

## Ingredient status

The old Green / Blue / Orange row colouring was removed because it could hide table text and the categories overlapped. Tables now show explicit Source, Mapping and Price status columns.

Only numeric `kg`, `L` and `each` recipe lines are automatically mapped. Cups, tins, bunches, spoons and unspecified quantities remain unconverted until confirmed.

## Private data

`data/private/` is ignored by Git. Keep Harbison source/reference files there unless Harbison explicitly approves public sharing.

## Upgrade and generate ML data

```powershell
pip install -r requirements.txt
python migrate_to_v6_ml.py
python generate_synthetic_data.py --start 2026-03-01 --end 2026-09-30 --seed 42 --intake-days 30 --residents-per-area 12
python -m streamlit run app.py
```

See `README_V6_ML.md` for the modelling assumptions and reporting guidance.
