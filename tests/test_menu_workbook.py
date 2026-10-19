import openpyxl

from src.intake import component_group_for, standard_plate
from src.menu_workbook import convert

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def _sheet(wb, title, rows):
    ws = wb.create_sheet(title)
    ws.append(["HARBISON MENU 2026 - WEEK 1"])
    ws.append(["MEAL"] + DAYS)
    for label, monday in rows:
        ws.append([label, monday] + [None] * 6)


def test_workbook_converts_every_diet(tmp_path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Menu Week 1", [("Breakfast", "Continental Breakfast"), ("Lunch Main Choice 1:", "Chicken Pie *"),
                               ("Lunch Main Choice 2:  ASF Members", "Mixed Grill"), ("Lunch Feature Veg", "Carrots, peas"),
                               ("Lunch Carbohydrate", "Chips"), ("Lunch Dessert", "Tiramisu"),
                               ("Evening Soup", "Minestrone Soup"), ("Evening Meal", "Sweet n Sour Fish"),
                               ("Unknown row", "ignored")])
    _sheet(wb, "Soft Bite Sized - Week 1 ", [("Lunch Main Choice 1:", "Chicken Mornay")])
    _sheet(wb, "Minced - Puree - Week 1", [("Morning Tea", "Custard, Yoghurt"), ("Puree:", "Chicken Mornay, Mash"),
                                           ("Minced:", "Chicken Mornay, Rice"), ("Puree:", "Fish, Mash"),
                                           ("Minced:", "Fish, Rice")])
    path = tmp_path / "menu.xlsx"
    wb.save(path)
    rows = convert(path)
    by = {(r["menu_variant"], r["meal_service"], r["component"]): r for r in rows}
    assert by[("Regular", "Lunch", "Main Choice 1")]["menu_label"] == "Chicken Pie *"
    assert by[("Regular", "Dinner", "Soup")]["menu_label"] == "Minestrone Soup"
    assert by[("Soft Bite Sized", "Lunch", "Main Choice 1")]["menu_label"] == "Chicken Mornay"
    assert by[("Puree", "Lunch", "Main")]["menu_label"] == "Chicken Mornay, Mash"
    assert by[("Minced", "Dinner", "Main")]["menu_label"] == "Fish, Rice"
    assert by[("Minced", "Morning Tea", "Morning tea")] and by[("Puree", "Morning Tea", "Morning tea")]
    assert {r["day_of_week"] for r in rows} == {0} and {r["week_number"] for r in rows} == {1}
    assert not [r for r in rows if r["menu_label"] == "ignored"]


def test_real_menu_components_map_to_groups_and_one_plate():
    items = [{"item_label": label, "menu_component": comp,
              "component_group": component_group_for(comp, cat, label), "food_item_id": None}
             for label, comp, cat in [
                 ("Chicken Pie", "Main Choice 1", "Main"), ("Mixed Grill", "Main Choice 2", "Main"),
                 ("Veggie Pie", "Vegetarian", "Vegetarian"), ("Carrots, peas", "Vegetables", "Vegetable"),
                 ("Chips", "Carbohydrate", "Carbohydrate"), ("Salad or Sandwiches", "Salad / Sandwich", "Salad / Sandwich"),
                 ("Tiramisu", "Dessert", "Dessert")]]
    groups = {i["item_label"]: i["component_group"] for i in items}
    assert groups == {"Chicken Pie": "protein", "Mixed Grill": "protein", "Veggie Pie": "protein",
                      "Carrots, peas": "vegetables", "Chips": "carbohydrate", "Salad or Sandwiches": "other",
                      "Tiramisu": "dessert"}
    plate = [i["item_label"] for i in standard_plate(items, "Lunch")]
    assert plate == ["Chicken Pie", "Carrots, peas", "Chips", "Tiramisu"]  # one main, not every option
    picked = [i["item_label"] for i in standard_plate(items, "Lunch", choose=lambda o: o[-1])]
    assert picked[0] == "Veggie Pie"
    assert standard_plate(items, "Morning Tea") == []
