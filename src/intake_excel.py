"""Presentable Excel report of low-intake items, reasons and nurse notes for dietitians."""
from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

TEAL = "176B55"
HEADER_FILL = PatternFill("solid", fgColor=TEAL)
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=TEAL)
SECTION_FONT = Font(bold=True, size=12, color=TEAL)
RED = PatternFill("solid", fgColor="F8D7DA")
AMBER = PatternFill("solid", fgColor="FFF3CD")
STRIPE = PatternFill("solid", fgColor="F4F8F6")
THIN = Side(style="thin", color="D9DEE3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def _table(ws: Worksheet, top: int, df: pd.DataFrame, widths: dict[str, int], pct_col: str | None = None) -> int:
    """Write a styled table starting at row `top`; returns the next free row."""
    for c, name in enumerate(df.columns, start=1):
        cell = ws.cell(row=top, column=c, value=name)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = max(ws.column_dimensions[get_column_letter(c)].width or 0,
                                                              widths.get(name, 14))
    for r, row in enumerate(df.itertuples(index=False), start=top + 1):
        for c, value in enumerate(row, start=1):
            if isinstance(value, float) and pd.isna(value):
                value = None
            cell = ws.cell(row=r, column=c, value=value)
            cell.border, cell.alignment = BORDER, WRAP
            if (r - top) % 2 == 0:
                cell.fill = STRIPE
            name = df.columns[c - 1]
            if name == pct_col and value is not None:
                cell.number_format = "0%"
                cell.alignment = Alignment(horizontal="center", vertical="top")
                cell.fill = RED if value <= 0.25 else AMBER if value <= 0.5 else cell.fill
            elif isinstance(value, (date, datetime)):
                cell.number_format = "dd mmm yyyy"
    return top + len(df) + 2


def build_report(items: pd.DataFrame, notes: pd.DataFrame, meta: dict) -> bytes:
    """items: Date, Meal, Resident, Room, Diet, Item, optional served/eaten gram detail, Eaten %, Reason, Recorded by.
    notes: Date, Meal, Resident, Room, Outcome, Note, Written by.
    meta: period, site, filters, generated_by."""
    items = items.copy()
    notes = notes.copy()
    if not items.empty:
        items["Eaten"] = items["Eaten"].str.rstrip("%").astype(float) / 100
        items["Date"] = pd.to_datetime(items["Date"]).dt.date
        items["Reason"] = items["Reason"].replace("", "Not given")
        items = items.rename(columns={"Eaten": "% eaten"})
    if not notes.empty:
        notes["Date"] = pd.to_datetime(notes["Date"]).dt.date

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Harbison Plate Waste - Low Intake Report"
    ws["A1"].font = TITLE_FONT
    info = [
        ("Period", meta.get("period", "")),
        ("Site", meta.get("site", "All sites")),
        ("Filters", meta.get("filters") or "None"),
        ("Downloaded by", meta.get("generated_by", "")),
        ("Downloaded on", datetime.now().strftime("%d %b %Y %H:%M")),
    ]
    for i, (k, v) in enumerate(info, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=v)
    row = 3 + len(info) + 1

    with_reason = items[items["Reason"] != "Not given"] if not items.empty else items
    ws.cell(row=row, column=1, value="Key numbers").font = SECTION_FONT
    numbers = [("Items eaten 50% or less", len(items)), ("Items with a reason given", len(with_reason)),
               ("Residents with low intake", items["Resident"].nunique() if not items.empty else 0),
               ("Nurse notes", len(notes))]
    for i, (k, v) in enumerate(numbers, start=row + 1):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=v).font = Font(bold=True)
    row += len(numbers) + 2

    if not with_reason.empty:
        ws.cell(row=row, column=1, value="Reasons for uneaten food").font = SECTION_FONT
        reasons = with_reason["Reason"].value_counts().rename_axis("Reason").reset_index(name="Times")
        reasons["Share"] = (reasons["Times"] / reasons["Times"].sum()).round(3)
        row = _table(ws, row + 1, reasons, {"Reason": 38, "Times": 10, "Share": 10})
        for r in range(row - len(reasons) - 1, row - 1):
            ws.cell(row=r, column=3).number_format = "0%"

    if not items.empty:
        ws.cell(row=row, column=1, value="By resident").font = SECTION_FONT
        by_resident = (items.groupby(["Resident", "Room", "Diet"], dropna=False)
                      .agg(**{"Items eaten 50% or less": ("Item", "size"),
                              "Average % eaten": ("% eaten", "mean"),
                              "Most common reason": ("Reason", lambda s: s[s != "Not given"].mode().iat[0]
                                                     if (s != "Not given").any() else "Not given")})
                      .reset_index().sort_values("Items eaten 50% or less", ascending=False))
        row = _table(ws, row + 1, by_resident, {"Resident": 24, "Room": 8, "Diet": 18, "Items eaten 50% or less": 14,
                                               "Average % eaten": 12, "Most common reason": 34},
                     pct_col="Average % eaten")
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 0, 30)
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 22)

    ws2 = wb.create_sheet("Low-intake items")
    ws2.sheet_view.showGridLines = False
    if items.empty:
        ws2["A1"] = "No items eaten 50% or less in this period."
    else:
        end = _table(ws2, 1, items, {"Date": 13, "Meal": 13, "Resident": 22, "Room": 8, "Diet": 17, "Item": 40,
                                     "Served (g)": 12, "Estimated eaten (g)": 16, "% eaten": 9,
                                     "Reason": 32, "Recorded by": 20}, pct_col="% eaten")
        ws2.freeze_panes = "A2"
        ws2.auto_filter.ref = f"A1:{get_column_letter(len(items.columns))}{end - 2}"
        ws2.cell(row=end, column=1, value="Red = 0-25% eaten, amber = 50% eaten.").font = Font(italic=True, color="666666")

    ws3 = wb.create_sheet("Nurse notes")
    ws3.sheet_view.showGridLines = False
    if notes.empty:
        ws3["A1"] = "No nurse notes in this period."
    else:
        end = _table(ws3, 1, notes, {"Date": 13, "Meal": 13, "Resident": 22, "Room": 8, "Outcome": 12, "Note": 60,
                                     "Written by": 20})
        ws3.freeze_panes = "A2"
        ws3.auto_filter.ref = f"A1:{get_column_letter(len(notes.columns))}{end - 2}"

    for sheet in (ws, ws2, ws3):
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToHeight = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
