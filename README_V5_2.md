# Harbison Food Waste Prototype V5.2

This update fixes the V5.1 issues while keeping the real Autumn/Winter menu and validated recipe integration.

## What changed

- Restored the Harbison supplier comparison dataset and graphs.
- Supplier information is comparison/reference only: no supplier recommendation, automatic product matching, or automatic quote-to-recipe pricing.
- Fixed Ingredients & Prices tables by removing fragile row-colour styling. Source, mapping and price state are now explicit text columns.
- Cleaned decorative icons that had been exported from the menu workbook as `?` / `??` characters.
- Record Waste now shows the real menu even before facility/service-area setup. Saving remains disabled until a real location is configured.
- Retains the four-week Regular, Soft Bite Sized, Minced and Puree menus.
- Retains validated soups plus selected dessert recipes suitable for reliable costing.

## Upgrade

After replacing the project files, run:

```powershell
pip install -r requirements.txt
python migrate_to_v5_2.py
python -m streamlit run app.py
```

The migration backs up the current database, restores supplier reference data, reimports and cleans the menu, reconciles recipes, and protects real waste records.
