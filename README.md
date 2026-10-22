# Harbison Food Waste Intelligence — Final Prototype

A Streamlit + SQLite prototype developed for **Harbison Care** to support food-waste recording, resident meal and consumption records, reporting, costing, and forecasting in residential aged care.

This repository contains the final capstone prototype developed by University of Canberra students for Project **2026-S2-37: Using Food Waste Metrics to Forecast and Address Meal Quality in Residential Aged Care**.

---

## Project Purpose

The prototype was designed to help Harbison:

- record food waste consistently across meal services
- distinguish production waste from plate waste
- monitor waste trends through dashboards and reports
- maintain menu, recipe and costing information
- record resident meal orders and consumption
- support future meal-quality and food-waste forecasting
- provide a foundation that can be extended into a production system

The current system is a **functional prototype / proof of concept**. It is not intended to be deployed directly as a production system containing real resident information without additional security, infrastructure and privacy controls.

---

## Main Features

### Food Waste Management

The Food Waste Management program includes:

- waste entry by date, location, meal and food item
- production waste recording
- automatic production-waste calculation from:
  - prepared quantity
  - served / plated quantity
- direct kitchen plate-waste recording in kilograms
- dashboards and reporting
- transaction history
- recipe and ingredient costing
- ingredient price management
- supplier comparison reference charts
- Harbison menu and location management
- CSV / structured data import
- ML-based preparation and plate-waste forecasting
- synthetic-data generation for development and model validation

### Resident Meal & Consumption Records

The resident component includes:

- resident details and room information
- dining-area allocation
- diet / texture information
- resident meal orders
- food served to each resident
- served food weight in grams
- percentage consumed
- estimated consumed weight
- meal reasons and notes
- resident import template
- meal and consumption history

Resident consumption records are kept separate from measured kitchen plate-waste records.

---

## Plate Waste Workflow

Plate waste is recorded as a **direct kitchen measurement**.

For each meal service, kitchen staff should:

1. collect the returned food leftovers from residents included in the selected service
2. combine the leftovers being measured
3. weigh the combined returned food
4. enter the measured value in kilograms into the Plate Waste section

Resident consumption percentages are useful for understanding meal acceptance at the individual level, but they are **not automatically treated as measured kitchen plate waste**.

---

## Production Waste Workflow

Production waste represents food that was prepared but not served.

The system calculates:

```text
Production Waste = Prepared Quantity - Served / Plated Quantity
```

Staff enter the prepared and served quantities, and the prototype calculates the production-waste amount automatically.

---

## Data Sources

The prototype currently supports two clearly separated data sources:

### Real Data

Real data includes records entered or imported from Harbison operational use.

Where approved and available, the prototype also uses Harbison reference information such as:

- Autumn/Winter 2026 four-week menu
- Regular, Soft & Bite-Sized, Minced & Moist and Pureed menu variants
- 12 Harbison soup recipes
- 2 selected dessert recipes with sufficiently clear serving and yield information
- supplier comparison covering 288 products
- confirmed ingredient pricing where available

### Synthetic Data

Synthetic data is used for:

- development
- testing
- dashboard demonstration
- resident workflow demonstration
- machine-learning development
- forecasting validation

Synthetic records are explicitly separated from real operational records.

The application does not intentionally combine real and synthetic records into a single reporting source.

---

## Synthetic Data Generation

Synthetic data is generated through one supported workflow:

```powershell
python generate_synthetic_data.py --start 2026-03-01 --end 2026-10-18 --seed 42 --intake-days 30 --residents-per-area 12
```

The generator creates:

- menu-aligned food-waste records
- resident demand
- preparation quantities
- production-waste records
- plate-waste patterns
- fictional resident meal and consumption records

The synthetic food-waste data follows the structure of the imported Harbison four-week menu while adding controlled variation for model development.

Synthetic records must not be interpreted as actual Harbison operational outcomes.

---

## Forecasting

The forecasting component includes two main prediction tasks:

### Preparation Quantity Forecast

Predicts expected food preparation quantity in kilograms.

### Plate-Waste / Meal-Quality Forecast

Predicts expected plate-waste percentage as an indication of likely meal acceptance and food-waste risk.

Model inputs may include:

- food item
- food category
- meal
- menu component
- location
- menu type
- resident count
- day/date context
- historical synthetic or available operational patterns

Model evaluation uses time-based validation rather than random train/test splitting.

Forecast results generated from synthetic data demonstrate the modelling workflow only and should not be presented as validated Harbison operational performance.

---

## Supplier Data

The Harbison supplier comparison contains approximately **288 products** and is retained for reference and price-comparison visualisation.

The prototype does **not**:

- automatically recommend suppliers
- treat supplier comparison data as purchase history
- automatically match every supplier product to recipes
- automatically apply supplier quotes to ingredient costing

Supplier information is therefore presented as reference data rather than a procurement recommendation system.

---

## Recipe and Ingredient Costing

Validated recipe data currently includes:

- 12 Harbison soup recipes
- 2 selected dessert recipes
- ingredient-level recipe information
- confirmed price mappings where sufficient information is available

Automatic costing is only performed where unit information and pricing are considered sufficiently reliable.

Numeric `kg`, `L` and `each` quantities can be mapped more safely.

Units such as:

- cups
- tins
- bunches
- spoons
- boxes
- unspecified quantities

may require manual confirmation or conversion before being used for reliable costing.

The application avoids presenting unknown ingredient costs as confirmed `$0` values.

---

## Resident Import Template

A blank resident import template is provided at:

```text
data/templates/Harbison_Resident_Import_Template.xlsx
```

The template contains the supported fields:

- Resident ID
- Name
- Room
- Dining area
- Diet
- Status

The facility/site is selected within the application before import and therefore does not need to be duplicated in the spreadsheet.

Completed resident files may contain personal information and should be stored only in approved private locations.

---

## Privacy and Data Handling

Private Harbison operational files and resident information must not be committed to the source repository.

The project `.gitignore` excludes locations such as:

```text
data/private/
data/raw/
data/import/
*.db
*.sqlite
*.sqlite3
.env
```

Real resident records, production databases and confidential sponsor files should remain in approved private storage.

Synthetic resident records used for development are fictional and must remain clearly identified as synthetic.

---

## Installation

### Requirements

Recommended environment:

- Python 3.11+
- Windows 10/11 or compatible operating system
- Streamlit
- Pandas
- Plotly
- scikit-learn
- NumPy
- openpyxl
- pytest

Install dependencies:

```powershell
pip install -r requirements.txt
```

---

## Running the Prototype

From the project directory:

```powershell
python -m streamlit run app.py
```

Streamlit will normally open the application at:

```text
http://localhost:8501
```

---

## Testing

Run the automated test suite with:

```powershell
python -m pytest -q
```

The final prototype test suite contains **46 automated tests** covering major functionality including resident import, intake records, location handling and menu workbook processing.

The final validated project version passed:

```text
46 passed
```

---

## Project Structure

Key folders and files include:

```text
app.py
requirements.txt

src/
    analytics.py
    auth.py
    db.py
    forecasting.py
    intake.py
    intake_db.py
    intake_excel.py
    locations.py
    menu_workbook.py
    resident_choices.py
    resident_import.py
    synthetic_data.py
    synthetic_intake.py
    textures.py

views/
    dashboard.py
    reports.py
    forecasting_page.py
    record_waste.py
    import_residents.py
    plate_waste.py
    reasons_notes.py
    sponsor_data.py
    synthetic_ml.py

data/
    templates/

docs/
    RESIDENT_MEAL_CONSUMPTION_RECORDS.md

tests/

generate_synthetic_data.py
import_menu_workbook.py
migrate_to_v7_intake.py
migrate_to_v7_2_measured_waste.py
migrate_to_v7_3_final_cleanup.py
```

---

## Handover

A separate sponsor handover package has been prepared for Harbison containing:

- Start Here guide
- User Guide
- Technical Handover Guide
- clean application source
- resident import template
- setup and run instructions
- future development guidance
- GitHub repository information

The GitHub repository provides the maintained source-code history for future technical teams.

Repository:

```text
https://github.com/Mac382005/harbison-food-waste-capstone
```

---

## Production Deployment Considerations

The current system should be treated as a prototype.

Before operational use with real resident data, Harbison should consider:

- production authentication
- formal role-based access control
- secure hosted database infrastructure
- database backup and recovery
- encryption and secure storage
- audit logging
- privacy and organisational governance review
- user acceptance testing
- integration with existing Harbison systems
- deployment and maintenance ownership
- data-retention requirements
- ongoing model validation using real operational data

SQLite and the current prototype login system are appropriate for demonstrating the solution but should be replaced or strengthened for a production deployment.

---

## Final Prototype Status

The final prototype demonstrates an end-to-end workflow covering:

**Menu and reference data → resident meal records → food-waste entry → costing → dashboards and reports → synthetic-data development → ML forecasting → sponsor handover**

The project provides Harbison with a working foundation that can be retained, evaluated and extended by a future software or IT team.

---

## Academic Project

Developed as part of:

**9785 ITS Capstone Project**  
University of Canberra  
Semester 2, 2026

Project:

**Using Food Waste Metrics to Forecast and Address Meal Quality in Residential Aged Care**

Industry Sponsor:

**Harbison Care**

This repository contains a university capstone prototype and should not be interpreted as a production clinical, dietary or operational information system.
