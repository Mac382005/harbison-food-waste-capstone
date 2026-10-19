# Plate Waste Management

A separate program inside the Harbison app for recording how much of each ordered item a resident ate.
It sits next to the existing **Food Waste Management** program and does not change it.

> **Status:** prototype with **synthetic residents only** (codes `DEMO-…`). The consumption figures are
> generated for software testing and are not Harbison outcomes.

## How it works

1. The first screen offers two programs: **Food Waste Management** and **Plate Waste Management**.
2. The user signs in to the chosen program. Each program only accepts the roles allowed to use it.
3. In Plate Waste Management, a nurse chooses the date, dining area and meal (Breakfast, Morning tea,
   Lunch, Afternoon tea, Dinner).
4. Residents appear as room buttons (✓ when done). Tapping one shows what they ordered for that meal:
   their meal from the four-week menu plus soup, water, juice, tea or coffee, jelly or ice cream.
5. For each item the nurse taps **0 / 25 / 50 / 75 / 100%** or **Not seen**, or marks the whole meal
   **Refused** or **Not there**. **Save** moves to the next resident.
6. The **All orders** tab shows every resident's orders for the day and what has been eaten.

## Loading the Harbison menu

The four-week menu comes from Harbison's menu workbook (Regular, Soft Bite Sized and Minced/Puree sheets
for Weeks 1-4). To load a new or updated workbook:

```powershell
.\.venv\Scripts\python.exe import_menu_workbook.py "C:\path\Autumn winter 2026.xlsx" --week1-start 2026-10-12
```

`--week1-start` is the Monday that menu Week 1 begins (it can also be changed in Menu & Locations). Each
resident's standard order is one plate from that day's menu for their diet: Main Choice 1 (or the Minced /
Puree meal), soup at dinner, vegetables, carbohydrate and dessert. Nurses can add the other options
(Main Choice 2, vegetarian, sandwiches) from **Today's menu** in **+ Add item**.

## What residents can order

**+ Add item** on the nurse screen: tap a group (Soups, Drinks, Desserts…), then tap the item and Add. Groups:
- **Today's menu**: the four-week-menu dishes for that meal and the resident's diet
- **Soups**: the 12 Harbison soup recipes (240 g serve), read from `data/private/reference/harbison_soups.csv`
- **Resident choices**: only products on the Harbison supplier comparison list (drinks, desserts,
  biscuits and snacks, breakfast cereals, hot food), renamed from pack sizes to what residents order
- **Other**: type any item

Ice cream and jelly are hidden for Minced & Moist and Pureed diets because they melt to thin liquid.

## Importing residents

Only **admins** have the **Import residents** page in Plate Waste Management.

**New site?** Open **Add a new site** at the top of the page, type the site name and its dining areas
(e.g. `Dining Area 1, Dining Area 2`) and press **Add site**. The site is created with its dining areas and
selected, ready for the upload. **Add dining area** next to the site list adds another area to an existing
site. Then choose the **Site** and upload that site's resident list; only that site's residents change.

1. **Download template** (or the sample) and fill in: Resident ID, Name, Room, Facility,
   Dining area, Diet (Regular, Soft & Bite-Sized, Minced & Moist, Pureed), Status (Active / Discharged). Common alternative headings such as "Bed",
   "Wing" or "Resident name" are recognised automatically.
2. Upload the CSV or Excel file. A preview shows what will happen to each row: **New**, **Update**
   (e.g. room 120 → 130), **Discharge**, **Re-admit**, **No change**, or a **problem** (missing room,
   unknown dining area, duplicate ID, unknown menu type…). Nothing is saved yet.
3. Press **Import**. Rows with problems are skipped.

Each person is recognised by **Resident ID**, so uploading an updated list moves people to new rooms and
hides discharged residents (their meal history is kept). Uploaded residents appear on the nurse screen
straight away. If a resident has no meal order, they get the standard order for that meal: the day's
menu items for their menu type plus water (tea or coffee and water at morning and afternoon tea).

Regenerating the demo data only replaces the generated `DEMO-` residents, never uploaded ones.

## Link to Food Waste Management

Every saved meal is sent straight into Food Waste Management as **Plate Waste** records, one per food
item: `kg wasted = portion size × (100% − % eaten)`. The portion comes from the item's recipe serving
size, or a standard portion for soup, jelly, ice cream and other extras. Drinks are not food waste and
are skipped. A **Refused** meal counts as 100% wasted; **Not there** and **Not seen** send nothing.
Editing a meal replaces its plate waste records, so nothing is counted twice.

In the Food Waste Dashboard and Reports, choose the data source **Plate waste data** to see
these records. They are kept apart from the synthetic and real food-waste data. The kg are estimates
from nurse observations, not weighed, so kitchens should not also weigh plate waste for the same meals.

"Not seen" is never counted as 0%. Saved records can't be overwritten: a dietitian or admin can
**Edit** a record, which keeps the original and saves a new version with a reason.

## Who can open what

| Role | Food Waste Management | Plate Waste Management | Edit saved meals |
|---|---|---|---|
| Nurse / Care Worker (`care`) | No | Yes | No |
| Dietitian | Yes | Yes | Yes |
| Administrator | Yes | Yes | Yes |
| Foodservice Manager | Yes | No | No |
| Kitchen | Yes | No | No |

## Data

| Table | Holds |
|---|---|
| `intake_residents` | Synthetic residents: code, room, facility, dining area, menu type |
| `intake_meal_orders` | What each resident ordered, per date and meal |
| `intake_meal_observations` | One record per resident, date and meal: Ate / Refused / Not there, with version history |
| `intake_component_observations` | Percentage eaten (or Not seen) for each ordered item |

Facilities, dining areas, meals, menu items and users are reused from the existing app. Plate waste
rows in `transactions` carry `intake_observation_id`, linking each one back to the nurse's record.
Database triggers stop synthetic and real records from mixing and stop saved records being edited in
place.

## Running locally (Windows PowerShell)

```powershell
cd $HOME\Documents\harbison-food-waste-capstone
.\.venv\Scripts\python.exe migrate_to_v7_intake.py        # backup + new tables (safe to re-run)
.\.venv\Scripts\python.exe generate_synthetic_data.py --start 2026-03-01 --end 2026-09-30 --seed 42
.\.venv\Scripts\python.exe -m pytest -q                   # tests
.\.venv\Scripts\python.exe -m streamlit run app.py        # http://localhost:8501
```

Run `generate_synthetic_resident_data.py` each day you demo: it creates orders up to today and leaves today's meals
blank for recording. Demo logins: `care / Care123!`, `dietitian / Dietitian123!`, `admin / Admin123!`,
`manager / Manager123!`, `kitchen / Kitchen123!`.
