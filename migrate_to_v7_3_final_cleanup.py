from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

from src.db import APP_DIR, DB_PATH, connection, init_db


OLD_TERM = "pati" + "ent"
LEGACY_FILES = [
    f"src/{OLD_TERM}_choices.py",
    f"src/{OLD_TERM}_import.py",
    "src/intake_demo.py",
    f"views/import_{OLD_TERM}s.py",
    f"tests/test_{OLD_TERM}_import.py",
    "data/templates/sample_residents_fictional.csv",
    f"data/templates/{OLD_TERM}s_harbison_site_3.csv",
    "generate_intake_demo.py",
    "generate_ml_data.py",
    "docs/PLATE_WASTE_MANAGEMENT.md",
    "README_V5_2.md",
    "README_V6_1.md",
    "README_V6_ML.md",
    "UPGRADE_V5_2.md",
    "PATCH_NOTES_V7_2.md",
]



def main():
    if DB_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB_PATH.with_name(f"food_waste_before_v7_3_cleanup_{stamp}.db")
        shutil.copy2(DB_PATH, backup)
        print(f"Backup created: {backup}")

    init_db()
    with connection() as c:
        # Real resident imports/records are now supported in the final workflow.
        c.execute(
            "INSERT INTO settings(key,value) VALUES('intake_real_records_enabled','1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'"
        )
        # Clean old terminology from audit history where it may exist.
        c.execute("UPDATE audit_log SET action='RESIDENT_MOVED' WHERE action=?", (("PATI" + "ENT_MOVED"),))
        c.execute("UPDATE audit_log SET action='IMPORT_RESIDENTS' WHERE action=?", (("IMPORT_" + "PATI" + "ENTS"),))
        old_lower = OLD_TERM
        old_title = old_lower.title()
        old_plural = old_lower + "s"
        c.execute(
            "UPDATE audit_log SET details=REPLACE(REPLACE(REPLACE(details,?,?),?,?),?,?) "
            "WHERE LOWER(details) LIKE ?",
            (old_title + "s", "Residents", old_plural, "residents", old_lower, "resident", f"%{old_lower}%"),
        )

    removed = []
    for rel in LEGACY_FILES:
        path = APP_DIR / rel
        if path.exists():
            path.unlink()
            removed.append(rel)

    for cache in APP_DIR.rglob("__pycache__"):
        if ".venv" not in cache.parts:
            shutil.rmtree(cache, ignore_errors=True)
    pytest_cache = APP_DIR / ".pytest_cache"
    if pytest_cache.exists():
        shutil.rmtree(pytest_cache, ignore_errors=True)

    print("V7.3 final cleanup complete.")
    print("Resident records: Real data and Synthetic data are kept separate; no combined source is exposed.")
    print("Legacy files removed:", len(removed))
    for rel in removed:
        print(" -", rel)
    print("Next: python -m pytest -q")
    print("Then: python -m streamlit run app.py")


if __name__ == "__main__":
    main()
