# Assessment Data Bundle

Generated: `2026-10-24T14:06:17+11:00`

This folder is the assessment/handover data snapshot for the final Harbison Food Waste prototype.

## Contents

- `csv/` â€” CSV export of every application database table from the final local prototype state.
- `csv/*__real.csv` and `csv/*__synthetic.csv` â€” split exports where a reliable source marker exists.
- `approved_source_files/` â€” sponsor/reference/raw/import files approved for assessment sharing.
- `templates/` â€” blank import templates.
- `DATABASE_TABLE_SUMMARY.csv` â€” table row counts and source-split information.
- `MANIFEST.csv` â€” file sizes and SHA-256 hashes.

## Interpretation

Synthetic records are for development, testing and ML validation and must not be interpreted as actual Harbison operational outcomes.

## Reproduce synthetic data

```powershell
python generate_synthetic_data.py --start 2026-03-01 --end 2026-10-18 --seed 42 --intake-days 30 --residents-per-area 12
```

## Database exported

`data/food_waste_v2.db`

## Database tables

- `audit_log`: 373 rows
- `facilities`: 2 rows
- `food_categories`: 16 rows
- `food_items`: 478 rows
- `harbison_menu_schedule`: 1442 rows
- `ingredient_price_history`: 46 rows
- `ingredients`: 46 rows
- `intake_clinical_reviews`: 0 rows
- `intake_component_observations`: 20624 rows
- `intake_meal_observations`: 7200 rows â€” real: 0, synthetic: 7200
- `intake_meal_orders`: 25143 rows â€” real: 0, synthetic: 25143
- `intake_residents`: 48 rows â€” real: 0, synthetic: 48
- `intake_review_criteria`: 4 rows
- `intake_review_events`: 0 rows
- `meals`: 6 rows
- `menu_item_recipe_links`: 0 rows
- `menu_schedule`: 0 rows
- `menu_settings`: 1 rows
- `recipe_ingredients`: 170 rows
- `recipes`: 53 rows
- `service_areas`: 4 rows
- `settings`: 2 rows
- `sponsor_recipe_ingredients`: 170 rows
- `sponsor_recipes`: 64 rows
- `supplier_products`: 272 rows
- `synthetic_generation_runs`: 1 rows
- `transactions`: 88112 rows â€” real: 0, synthetic: 88112
- `users`: 5 rows

## Approved source files copied

- `data/private`: 8 files

## Security

Environment files, virtual environments, Python caches, SQLite database binaries/backups, and secret/password/token values are not included in GitHub.
Potential credential columns in CSV exports are replaced with `[REDACTED]`.
