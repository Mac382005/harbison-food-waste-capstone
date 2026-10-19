"""Add the Resident Meal & Consumption Records tables and the Care Worker role.

Safe to run more than once. Takes a backup first, only adds new tables, and rebuilds the
users table (keeping every row and ID) only if the 'care' role is not yet allowed.
"""
import shutil
from datetime import datetime

from src.db import DB_PATH, connection, fetchone, init_db
from src.seed import seed_core

if __name__ == "__main__":
    if DB_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB_PATH.with_name(f"food_waste_before_v7_intake_{stamp}.db")
        shutil.copy2(DB_PATH, backup)
        print(f"Backup created: {backup}")

    before = fetchone("SELECT COUNT(*) n FROM transactions")["n"] if DB_PATH.exists() else 0
    init_db()
    seed_core()
    with connection() as c:
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = c.execute("PRAGMA foreign_key_check").fetchall()
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'intake_%' ORDER BY name")]
        after = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    print("V7 intake migration complete.")
    print("Integrity check:", integrity, "| foreign key problems:", len(fk_errors))
    print("Intake tables:", ", ".join(tables))
    print(f"Food waste transactions before/after: {before}/{after}")
    print("Demo login for care staff: care / Care123!")
    print("Next: python generate_synthetic_resident_data.py   (synthetic residents, orders and meals)")
