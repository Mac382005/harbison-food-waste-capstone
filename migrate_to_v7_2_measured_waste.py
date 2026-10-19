from __future__ import annotations

from datetime import datetime
import sqlite3

from src.db import DB_PATH, connection, init_db


def main():
    if DB_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = DB_PATH.with_name(f"food_waste_before_v7_2_{stamp}.db")
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close(); src.close()
        print(f"Backup created: {backup_path}")

    init_db()  # adds served_weight_g to resident component records
    with connection() as c:
        old = c.execute("SELECT COUNT(*) FROM transactions WHERE intake_observation_id IS NOT NULL").fetchone()[0]
        c.execute("DELETE FROM transactions WHERE intake_observation_id IS NOT NULL")
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
    print("V7.2 measured-waste migration complete.")
    print(f"Removed legacy percentage-derived plate-waste rows: {old}")
    print(f"Foreign key problems: {len(fk)}")
    print("Resident intake percentages are now descriptive only; kitchen plate waste must be weighed and entered directly.")


if __name__ == "__main__":
    main()
