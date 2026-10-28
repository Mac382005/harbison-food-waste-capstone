# Harbison Food Waste Intelligence — Final Prototype

A Streamlit + SQLite prototype developed for **Harbison Care** to support food-waste recording, resident meal and consumption records, reporting, recipe costing and forecasting in residential aged care.

**University of Canberra — ITS Capstone 9785, Semester 2 2026**  
**Project 2026-S2-37:** *Using Food Waste Metrics to Forecast and Address Meal Quality in Residential Aged Care*

Public repository:  
**https://github.com/Mac382005/harbison-food-waste-capstone**

---

## Project Overview

The prototype provides two connected programs:

### Food Waste Management
Supports:

- production-waste recording
- directly measured kitchen plate-waste recording
- transaction history
- dashboards and reports
- recipe and ingredient costing
- ingredient price management
- Harbison menu and location management
- supplier-reference data
- synthetic-data generation
- machine-learning forecasting

### Resident Meal & Consumption Records
Supports:

- fictional/demo resident records
- resident room and dining-area information
- diet / texture information
- meal orders
- served food weight
- observed intake percentage
- estimated consumed quantity
- reasons and notes
- resident import using the supplied Excel template

Resident consumption records are kept separate from directly measured kitchen plate-waste records.

---

# Quick Start — Fresh Clone

The following steps create a complete local prototype with synthetic data for demonstration, screenshots and testing.

## 1. Download the source

```powershell
git clone https://github.com/Mac382005/harbison-food-waste-capstone.git
cd harbison-food-waste-capstone
```

## 2. Create the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Verify the installation

Run the automated test suite before starting the application:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected final result:

```text
46 passed
```

## 4. Restore the approved Harbison reference files

The working folder `data/private/reference/` is intentionally excluded from Git.

Approved assessment copies are provided in:

```text
data/deliverable/approved_source_files/data__private/reference/
```

Create the local reference folder and copy the files:

```powershell
New-Item -ItemType Directory -Force ".\data\private\reference" | Out-Null

Copy-Item `
  ".\data\deliverable\approved_source_files\data__private\reference\*" `
  ".\data\private\reference\" `
  -Force
```

This provides the local application with the approved menu, recipe and supplier-reference files.

## 5. Import the Harbison reference data

```powershell
.\.venv\Scripts\python.exe .\migrate_to_v5_2.py
```

The final Harbison menu contains **1,442 schedule rows** across the supported menu variants.

## 6. Generate the synthetic demonstration dataset

```powershell
.\.venv\Scripts\python.exe .\generate_synthetic_data.py `
  --start 2026-03-01 `
  --end 2026-10-18 `
  --seed 42 `
  --intake-days 30 `
  --residents-per-area 12
```

The final validated generation produced:

| Dataset | Final count |
|---|---:|
| Harbison menu rows | 1,442 |
| Synthetic waste transactions | 88,112 |
| Fictional residents | 48 |
| Resident meal observations | 7,200 |
| Resident meal-order rows | 25,143 |

Synthetic records are for development, demonstration and ML validation only. They are **not real Harbison operational outcomes**.

## 7. Run the prototype

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit normally opens at:

```text
http://localhost:8501
```

---

# Demo Accounts

For prototype demonstration only:

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `Admin123!` |
| Foodservice Manager | `manager` | `Manager123!` |
| Kitchen Staff | `kitchen` | `Kitchen123!` |
| Dietitian / Analyst | `dietitian` | `Dietitian123!` |
| Care Worker | `care` | `Care123!` |

These are demonstration credentials and must be replaced before any production deployment.

For reviewing the complete prototype, use:

```text
admin / Admin123!
```

---

# Food-Waste Workflows

## Production Waste

Production waste represents food that was prepared but not served.

The prototype calculates:

```text
Production Waste = Prepared Quantity - Served / Plated Quantity
```

Staff enter prepared and served quantities and the system calculates the waste amount and percentage.

## Plate Waste

Plate waste is recorded as a **direct kitchen measurement**.

Kitchen staff:

1. collect returned leftovers from the selected meal service;
2. combine the leftovers being measured;
3. weigh the returned food;
4. enter the measured total in kilograms.

Resident intake percentages are **not automatically converted into measured plate-waste kilograms**.

This keeps individual meal-consumption observations separate from kitchen waste measurements.

---

# Dashboard, Reports and Forecasting

The prototype includes:

- total production and plate waste
- waste trends over time
- meal-service comparisons
- location/service-area analysis
- food items with high waste
- plate-waste KPI monitoring
- preparation forecasting
- expected plate-waste forecasting

Forecasting uses a **time-based holdout** rather than a random train/test split.

The current model evaluation is based on synthetic development data and demonstrates the forecasting workflow only. It must not be interpreted as validated Harbison operational performance.

---

# Final Assessment Data

The final assessment dataset is available at:

```text
data/deliverable/
```

Important contents include:

```text
data/deliverable/
├── DATA_README.md
├── DATABASE_TABLE_SUMMARY.csv
├── MANIFEST.csv
├── csv/
├── approved_source_files/
└── templates/
```

Final exported database state includes:

| Item | Count |
|---|---:|
| Menu schedule rows | 1,442 |
| Food items | 478 |
| Supplier products | 272 |
| Costing recipes | 53 |
| Sponsor recipe records | 64 |
| Recipe ingredient rows | 170 |
| Synthetic waste transactions | 88,112 |
| Real waste transactions | 0 |
| Fictional residents | 48 |
| Real residents | 0 |
| Resident meal observations | 7,200 |
| Resident meal orders | 25,143 |

`MANIFEST.csv` contains file sizes and SHA-256 hashes for the assessment data bundle.

---

# Data Sources and Interpretation

The repository contains three different types of information that should not be confused.

### Sponsor / reference data
Includes the approved Harbison menu, recipe and supplier-reference information used to build the prototype.

### Synthetic data
Generated specifically for:

- software development
- demonstration
- dashboard testing
- resident workflow testing
- machine-learning development and validation

### Real operational data
The final public assessment dataset contains **no real waste transactions and no real resident records**.

Real operational information should only be added in an approved secure Harbison environment.

---

# Recipe and Costing Data

The prototype stores sponsor/reference recipe information and ingredient-level costing data.

Automatic costing is only used where quantity, unit and price information are sufficiently reliable.

Units such as:

- kg
- L
- each

can be mapped directly where appropriate.

Unclear quantities or kitchen-specific units should be confirmed before they are used for operational costing.

Unknown costs are not intentionally presented as confirmed `$0` values.

---

# Resident Import

A blank Excel template is available at:

```text
data/templates/Harbison_Resident_Import_Template.xlsx
```

Supported fields include:

- Resident ID
- Name
- Room
- Dining area
- Diet
- Status

The site/facility is selected in the application before the file is imported.

Any completed file containing real resident information should be stored only in an approved private environment.

---

# Project Structure

```text
harbison-food-waste-capstone/
│
├── app.py
├── requirements.txt
├── generate_synthetic_data.py
├── prepare_assessment_data.py
│
├── data/
│   ├── templates/
│   └── deliverable/
│       ├── DATA_README.md
│       ├── DATABASE_TABLE_SUMMARY.csv
│       ├── MANIFEST.csv
│       ├── csv/
│       ├── approved_source_files/
│       └── templates/
│
├── src/
├── views/
├── tests/
└── docs/
```

Key areas:

- `app.py` — Streamlit application entry point
- `src/` — database, analytics, forecasting, imports and business logic
- `views/` — Streamlit pages
- `tests/` — automated test suite
- `data/templates/` — blank import templates
- `data/deliverable/` — final assessment datasets and approved reference files

---

# Testing and Quality Assurance

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Final validated result:

```text
46 passed
```

Quality assurance also included:

- repeated sponsor review and workflow refinement
- real/synthetic data separation
- database migration and integrity checks
- terminology cleanup from patient to resident
- final dataset/export checks
- Git feature branches and pull-request integration
- final clean `main` branch
- review of reference-data provenance and costing limitations

---

# Privacy and Security

The prototype is a university proof of concept.

The repository excludes working locations such as:

```text
data/private/
data/raw/
data/import/
*.db
*.sqlite
*.sqlite3
.env
```

Credential/password fields in assessment CSV exports are redacted.

Before use with real resident information, Harbison should implement appropriate:

- secure authentication
- role-based access control
- secure hosted database infrastructure
- backup and recovery
- audit logging
- privacy and data-retention controls
- organisational approval
- user acceptance testing

---

# Production Status

This system is a **functional prototype / proof of concept**, not a production clinical or operational system.

Recommended next steps are:

1. pilot the waste-recording workflow in a controlled service area;
2. establish a consistent measurement protocol;
3. collect sufficient real food-waste history;
4. retrain and evaluate forecasting models using real operational data;
5. strengthen authentication, infrastructure, privacy and backup controls;
6. assign ownership for menu, recipe, price and location maintenance.

---

# Project Team

University of Canberra — ITS Capstone 9785  
Semester 2, 2026

**Project 2026-S2-37**  
*Using Food Waste Metrics to Forecast and Address Meal Quality in Residential Aged Care*

Industry Sponsor: **Harbison Care**

Team:

- Hoang Nhat Minh Mac
- Tri Le
- Nima Tshering
- Lyn Nguyen

---

## Final Deliverable Status

The final prototype demonstrates the complete workflow:

**Harbison reference data → resident meal records → waste recording → costing → dashboards and reports → synthetic-data development → ML forecasting → sponsor handover**

The repository contains the working prototype, final assessment datasets, templates, automated tests and documentation required to review and continue the project.
