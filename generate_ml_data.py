from __future__ import annotations

import argparse
from datetime import date

from src.db import init_db
from src.menu_import import ensure_menu_loaded
from src.synthetic_data import GenerationConfig, generate_synthetic_ml_data


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD") from exc


def main():
    parser = argparse.ArgumentParser(description="Generate menu-aligned synthetic ML data for the Harbison prototype.")
    parser.add_argument("--start", type=parse_date, default=date(2026, 3, 1), help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date, default=date(2026, 9, 30), help="End date YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=42, help="Reproducible random seed")
    parser.add_argument("--resident-min", type=int, default=44, help="Minimum residents per dining area")
    parser.add_argument("--resident-max", type=int, default=56, help="Maximum residents per dining area")
    parser.add_argument("--facilities", type=int, default=2, help="Synthetic facilities only if no configured locations exist")
    parser.add_argument("--areas", type=int, default=2, help="Dining areas per synthetic facility")
    parser.add_argument("--keep-existing", action="store_true", help="Append a new run instead of replacing generated ML data")
    args = parser.parse_args()

    init_db()
    if not ensure_menu_loaded():
        raise SystemExit("No Harbison menu is available. Reconcile/import the menu first.")

    result = generate_synthetic_ml_data(
        GenerationConfig(
            start_date=args.start,
            end_date=args.end,
            seed=args.seed,
            resident_min=args.resident_min,
            resident_max=args.resident_max,
            fallback_facilities=args.facilities,
            fallback_areas_per_facility=args.areas,
            replace_existing=not args.keep_existing,
        )
    )
    print("Synthetic ML generation complete.")
    for key, value in result.items():
        print(f"{key}: {value}")
    print("All generated rows are marked synthetic and can be selected separately in Dashboard, Reports and Forecasting.")


if __name__ == "__main__":
    main()
