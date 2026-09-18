from datetime import datetime
import shutil

from src.db import init_db, DB_PATH
from src.sponsor_import import import_default_sponsor_files, retire_legacy_demo_data
from src.menu_import import import_harbison_menu


if __name__ == "__main__":
    if DB_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB_PATH.with_name(f"food_waste_before_v5_2_{stamp}.db")
        shutil.copy2(DB_PATH, backup)
        print(f"Backup created: {backup}")

    init_db()
    sponsor = import_default_sponsor_files()
    menu_rows = import_harbison_menu()
    legacy = retire_legacy_demo_data()

    print("V5.2 migration complete.")
    print("Sponsor reference import:", sponsor)
    print("Menu rows:", menu_rows)
    print("Legacy cleanup:", legacy)
    print("Supplier comparison restored as reference analytics only; no supplier recommendation or auto-pricing.")
    print("Menu labels were cleaned of exported decorative '?' characters.")
    print("Next: run `python -m streamlit run app.py`.")
