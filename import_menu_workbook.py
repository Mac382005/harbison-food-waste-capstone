"""Load the Harbison four-week menu from the Excel workbook.

Usage:
    python import_menu_workbook.py "C:/path/Autumn winter 2026.xlsx" --week1-start 2026-10-12
"""
from __future__ import annotations

import argparse
import shutil
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from src.db import execute, init_db
from src.menu_import import MENU_FILE, import_harbison_menu
from src.menu_workbook import convert, write_csv


def main():
    parser = argparse.ArgumentParser(description="Convert and load the Harbison menu workbook.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--week1-start", type=date.fromisoformat, help="Monday that menu Week 1 starts (YYYY-MM-DD)")
    args = parser.parse_args()

    rows = convert(args.workbook)
    if not rows:
        raise SystemExit("No menu rows found. Check the workbook has the 'MEAL | MONDAY ... SUNDAY' sheets.")
    if MENU_FILE.exists():
        backup = MENU_FILE.with_name(f"{MENU_FILE.stem}.before-{datetime.now():%Y%m%d-%H%M%S}.csv.bak")
        shutil.copy2(MENU_FILE, backup)
        print(f"Previous menu file backed up to {backup.name}")
    MENU_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, MENU_FILE)

    init_db()
    loaded = import_harbison_menu()
    if args.week1_start:
        if args.week1_start.weekday() != 0:
            raise SystemExit("Week 1 must start on a Monday.")
        execute("UPDATE menu_settings SET cycle_start_date=? WHERE id=1", (args.week1_start.isoformat(),))
    print(f"Menu rows converted: {len(rows)} | loaded: {loaded}")
    print("By diet:", dict(Counter(r["menu_variant"] for r in rows)))
    if args.week1_start:
        print(f"Week 1 starts {args.week1_start:%A %d %b %Y}")


if __name__ == "__main__":
    main()
