# Upgrade to V5.2

1. Stop Streamlit (`Ctrl+C`).
2. Replace the project with the V5.2 files.
3. Keep your existing `data/food_waste_v2.db` if you want to preserve existing users/settings/real records.
4. Run:

```powershell
pip install -r requirements.txt
python migrate_to_v5_2.py
python -m streamlit run app.py
```

Expected migration results include roughly 288 supplier rows, 14 validated recipes, 165 recipe lines, 110 safe costing mappings, and 1,442 menu rows.

After launch, check:
- Harbison Data -> Supplier comparison
- Ingredients & Prices
- Menu & Locations -> Four-week menu
- Record Waste
