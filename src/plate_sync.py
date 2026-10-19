"""Legacy compatibility module.

Resident meal-consumption percentages are no longer converted into kilograms of plate waste.
Measured plate waste must be weighed by kitchen staff and entered on the Food Waste Management
Record Waste page. These no-op functions remain only so older local code cannot accidentally
recreate percentage-derived waste rows.
"""
from __future__ import annotations


def sync_plate_waste(observation_ids: list[int] | None = None, data_source: str | None = None) -> int:
    return 0


def plate_waste_for(observation_id: int) -> float | None:
    return None
