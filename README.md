# Harbison Food Waste Intelligence — V2

This is the upgraded capstone prototype for **2026-S2-37**.

## Major V2 upgrades

- Real multi-page Streamlit navigation.
- Prototype login and role-based access.
- Passwords are stored using PBKDF2 hashing, not plain text.
- Raw-material ingredient price history.
- Recipe-based finished-food costing.
- Historical transaction cost snapshots.
- 90-day synthetic data generator covering **every active facility, service area and all six meal services**.
- Seeded configuration produces approximately **8,640 synthetic transactions**, instead of 24,000+.
- Improved dashboard:
  - KPI breach **rate** with context;
  - highest total waste in kg;
  - highest average plate-waste percentage separately.
- Audit log for important administrative actions.
- More polished UI styling.

## Prototype accounts

| Username | Password | Role |
|---|---|---|
| admin | Admin123! | System Administrator |
| manager | Manager123! | Foodservice Manager |
| kitchen | Kitchen123! | Kitchen Staff |
| dietitian | Dietitian123! | Dietitian / Analyst |

These credentials are for demonstration only.

## Access model

### Kitchen Staff
- Record Waste
- Transactions

### Foodservice Manager
- Dashboard
- Record Waste
- Transactions
- Reports
- Forecasting
- Ingredients & Prices
- Recipes & Costing
- Menu & Locations

### Dietitian / Analyst
- Dashboard
- Transactions
- Reports
- Forecasting

### System Administrator
- Full access, including Users & Access and System Admin.

## Raw-material pricing workflow

1. Manager/Admin opens **Ingredients & Prices**.
2. Selects an ingredient.
3. Enters the supplier pack quantity and purchase price.
4. The system calculates the current unit cost (e.g. A$/kg).
5. Recipe costing automatically uses the newest price effective on that date.
6. New waste records snapshot the resulting finished-food cost/kg.
7. Existing historical waste transactions **do not change** when a later ingredient price is entered.

Example:

```text
Chicken breast 10 kg pack = A$101
Unit cost = A$10.10/kg

Chicken Casserole recipe uses 10 kg chicken + other ingredients
Recipe batch cost / finished yield = derived cost per kg

4.5 kg wasted × derived finished-food cost/kg
= estimated waste cost
```

## Synthetic data

The generator uses 90 calendar days.

For every day it covers:

- both seeded facilities;
- every active service area;
- Breakfast;
- Morning Tea;
- Lunch;
- Afternoon Tea;
- Dinner;
- Snacks.

For each service-area/meal combination, it records one rotating menu item with:
- one Production Waste transaction;
- one Plate Waste transaction.

With 8 seeded service areas:

```text
90 days × 8 areas × 6 meals × 2 waste types = 8,640 transactions
```

The food item rotates through the relevant menu so the dataset does not always test the same food.

## Run V2

From the folder containing `app.py`:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The database is created automatically at:

```text
data/food_waste_v2.db
```

### First test

1. Sign in as `admin / Admin123!`.
2. Open **System Admin**.
3. Click **Generate 90-day synthetic dataset**.
4. Open **Dashboard**.
5. Test the other roles by signing out and logging in with their demo accounts.

## Important limitations

- This is still a capstone prototype, not production security.
- No MFA, SSO, password-reset email or enterprise identity provider.
- User passwords are hashed, but deployment hardening is still required.
- No direct electronic scale/IoT integration.
- No procurement-system or supplier API integration.
- Ingredient and recipe data are demonstration values until Harbison provides real recipes/order logs.
- Forecasting is decision support only and should not automatically reduce food provision or place orders.
