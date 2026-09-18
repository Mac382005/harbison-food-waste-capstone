# Harbison Food Waste Intelligence - V5.2

A Streamlit + SQLite prototype for recording and analysing food waste in residential aged care using Harbison reference data.

## Data currently used

- Autumn/Winter 2026 four-week menu
- Regular, Soft Bite Sized, Minced and Puree menu variants
- 12 Harbison soup recipes
- 2 selected dessert recipes with sufficiently clear serving/yield data
- Harbison supplier comparison (288 products) for reference charts and comparison only
- manual confirmed ingredient prices for recipe costing
- real waste records entered in the app or imported from CSV/Excel

## Supplier scope

Supplier comparison is kept because it is useful operational reference data and provides useful charts. The app does **not** recommend a supplier, automatically match supplier products to recipes, or automatically apply supplier quotes to costing.

## Ingredient status

The old Green / Blue / Orange row colouring was removed because it could hide table text and the categories overlapped. The tables now show explicit columns for:

- **Source** - Harbison recipe or Manual/general
- **Mapping** - mapped ingredient or Needs confirmation
- **Price status** - Added, Needed or Not mapped

Only numeric `kg`, `L` and `each` recipe lines are automatically mapped. Cups, tins, bunches, spoons and unspecified quantities remain unconverted until confirmed.

## Record Waste workflow

1. Choose service date.
2. Choose menu type.
3. Choose meal and menu component.
4. Choose only from items actually scheduled on the imported Harbison menu.
5. Choose facility/service area if configured.
6. Enter production or plate waste and save.

The menu can be previewed even before facility/service-area names are configured. Saving is disabled until a real location is selected.

## Private data

`data/private/` is ignored by Git. Keep Harbison source/reference files there unless Harbison explicitly approves public sharing.

## Run / upgrade

```powershell
pip install -r requirements.txt
python migrate_to_v5_2.py
python -m streamlit run app.py
```
