from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.db import init_db
from src.menu_import import ensure_menu_loaded
from src.seed import seed_core
from src.synthetic_data import GenerationConfig, generate_synthetic_ml_data
from src.synthetic_intake import generate_synthetic_resident_data


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD") from exc


def main():
    parser = argparse.ArgumentParser(description="Generate all synthetic prototype data in one run.")
    parser.add_argument("--start", type=parse_date, default=date(2026, 3, 1))
    parser.add_argument("--end", type=parse_date, default=date(2026, 9, 30))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resident-min", type=int, default=44)
    parser.add_argument("--resident-max", type=int, default=56)
    parser.add_argument("--facilities", type=int, default=2)
    parser.add_argument("--areas", type=int, default=2)
    parser.add_argument("--intake-days", type=int, default=30)
    parser.add_argument("--residents-per-area", type=int, default=12)
    args = parser.parse_args()

    init_db()
    seed_core()
    if not ensure_menu_loaded():
        raise SystemExit("No Harbison menu is available. Reconcile/import the menu first.")

    waste = generate_synthetic_ml_data(GenerationConfig(
        start_date=args.start, end_date=args.end, seed=args.seed,
        resident_min=args.resident_min, resident_max=args.resident_max,
        fallback_facilities=args.facilities, fallback_areas_per_facility=args.areas,
        replace_existing=True,
    ))
    intake_end = min(args.end, date.today() - timedelta(days=1))
    if intake_end >= args.start:
        intake_start = max(args.start, intake_end - timedelta(days=max(1, args.intake_days) - 1))
        intake = generate_synthetic_resident_data(intake_start, intake_end, args.residents_per_area, args.seed)
    else:
        intake = {"residents": 0, "orders": 0, "meals_recorded": 0, "items_recorded": 0}

    print("Unified synthetic-data generation complete.")
    print(f"waste_transactions: {waste['transactions']}")
    print(f"menu_rows_used: {waste['menu_rows_used']}")
    print(f"synthetic_residents: {intake['residents']}")
    print(f"resident_meals_recorded: {intake['meals_recorded']}")
    print("Real operational records were not touched.")


if __name__ == "__main__":
    main()
