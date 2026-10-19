# V7.3 final workflow cleanup

This patch focuses on the final handover workflow.

- Resident import now provides one blank template download only.
- The template is site-specific: Facility is no longer required in the CSV because the site is selected in the app.
- Forecasting exposes only **Synthetic data** or **Real data**. There is no mixed source option.
- Resident meal records also keep real and synthetic records separate.
- Plate-waste entry explains the kitchen workflow: returned leftovers from residents for the meal service are combined and weighed, then the measured kg is entered directly.
- Production waste remains calculated automatically from Prepared kg minus Served / plated kg.
- Supplier legend chips are readable in both light and dark themes.
- Resident terminology is used throughout project code, tests and documentation.
- Old standalone synthetic generators are removed; `generate_synthetic_data.py` is the supported combined generator.
- Legacy files and old audit terminology are removed by `migrate_to_v7_3_final_cleanup.py`.

- Legacy version notes that described mixed-source workflows are removed during cleanup so the final repo documents only the current real-vs-synthetic workflow.
