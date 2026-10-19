from datetime import datetime
import shutil

from src.db import init_db, DB_PATH, fetchone
from src.sponsor_import import import_default_sponsor_files
from src.menu_import import ensure_menu_loaded


if __name__ == "__main__":
    if DB_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB_PATH.with_name(f"food_waste_before_v6_ml_{stamp}.db")
        shutil.copy2(DB_PATH, backup)
        print(f"Backup created: {backup}")

    init_db()
    sponsor = import_default_sponsor_files()
    menu_rows = ensure_menu_loaded()
    synthetic_rows = fetchone("SELECT COUNT(*) n FROM transactions WHERE synthetic_run_id IS NOT NULL")["n"]

    print("V6 ML migration complete.")
    print("Sponsor reference import:", sponsor)
    print("Harbison menu rows:", menu_rows)
    print("Existing synthetic ML rows:", synthetic_rows)
    print("New ML schema is ready; real and synthetic transactions remain separated.")
    print("Next: run `python generate_synthetic_data.py --start 2026-03-01 --end 2026-09-30 --seed 42 --intake-days 30 --residents-per-area 12`.")
    print("Then run `python -m streamlit run app.py`.")
