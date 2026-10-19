"""Convert the Harbison menu workbook (Excel) into the four-week menu CSV the app imports.

Workbook layout (one sheet per week and diet):
- 'Menu Week N'                 -> Regular
- 'Soft Bite Sized - Week N'    -> Soft Bite Sized
- 'Minced - Puree - Week N'     -> Minced and Puree ('Puree:' / 'Minced:' rows are diet-specific; the first
                                   pair is lunch, the second pair is the evening meal; other rows apply to both)
Each sheet has a 'MEAL | MONDAY ... SUNDAY' header row; the first column names the menu row.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import openpyxl

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

# workbook row label -> (meal service, component, category). Categories match the synthetic-data portions.
ROWS = {
    "breakfast": ("Breakfast", "Continental", "Breakfast"),
    "breakfast - asf": ("Breakfast", "Hot breakfast", "Breakfast"),
    "morning tea": ("Morning Tea", "Morning tea", "Tea / Snack"),
    "lunch main choice 1": ("Lunch", "Main Choice 1", "Main"),
    "lunch main choice 2": ("Lunch", "Main Choice 2", "Main"),
    "lunch feature veg": ("Lunch", "Vegetables", "Vegetable"),
    "lunch carbohydrate": ("Lunch", "Carbohydrate", "Carbohydrate"),
    "salads and sandwiches available all day": ("Lunch", "Salad / Sandwich", "Salad / Sandwich"),
    "vegetarian option": ("Lunch", "Vegetarian", "Vegetarian"),
    "lunch dessert": ("Lunch", "Dessert", "Dessert"),
    "afternoon tea": ("Afternoon Tea", "Afternoon tea", "Tea / Snack"),
    "evening soup": ("Dinner", "Soup", "Soup"),
    "evening meal": ("Dinner", "Main", "Main"),
    "dinner feature veg": ("Dinner", "Vegetables", "Vegetable"),
    "dinner carbohydrate": ("Dinner", "Carbohydrate", "Carbohydrate"),
    "vegetarian evening": ("Dinner", "Vegetarian", "Vegetarian"),
    "evening dessert": ("Dinner", "Dessert", "Dessert"),
}


def _key(label) -> str:
    text = re.sub(r"\s+", " ", str(label or "")).strip().lower().rstrip(":").strip()
    return re.sub(r":.*$", "", text).strip() if text.startswith("lunch main choice") else text


def _sheet_variants(title: str):
    t = title.lower()
    week = int(re.search(r"week\s*(\d)", t).group(1))
    if "minced" in t or "puree" in t:
        return week, ["Minced", "Puree"]
    if "soft" in t:
        return week, ["Soft Bite Sized"]
    return week, ["Regular"]


def convert(workbook: Path, source_name: str | None = None) -> list[dict]:
    wb = openpyxl.load_workbook(workbook, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        try:
            week, variants = _sheet_variants(ws.title)
        except AttributeError:
            continue
        day_cols, diet_rows_seen = None, {"puree": 0, "minced": 0}
        for row in ws.iter_rows(values_only=True):
            cells = list(row)
            if not cells or cells[0] in (None, ""):
                continue
            first = str(cells[0]).strip()
            if first.upper() == "MEAL":
                day_cols = {i: DAYS.index(str(v).strip().upper()) for i, v in enumerate(cells)
                            if v and str(v).strip().upper() in DAYS}
                continue
            if day_cols is None:
                continue
            key = _key(first)
            if key in ("puree", "minced"):
                diet_rows_seen[key] += 1
                meal = "Lunch" if diet_rows_seen[key] == 1 else "Dinner"
                spec = (meal, "Main", "Main")
                row_variants = ["Puree"] if key == "puree" else ["Minced"]
            elif key in ROWS:
                spec, row_variants = ROWS[key], variants
            else:
                continue
            meal, component, category = spec
            for col, dow in day_cols.items():
                value = cells[col] if col < len(cells) else None
                label = re.sub(r"\s+", " ", str(value or "")).strip()
                if not label:
                    continue
                for variant in row_variants:
                    out.append({
                        "menu_label": label, "category": category, "menu_variant": variant,
                        "week_number": week, "day_of_week": dow, "day_name": DAYS[dow].title(),
                        "meal_service": meal, "component": component, "linked_recipe": "",
                        "source_sheet": ws.title.strip(), "source_document": source_name or workbook.name,
                    })
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
