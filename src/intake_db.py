"""Schema for Resident Meal & Consumption Records (resident meal orders and consumption).

Design rules:
- Residents are identified by a pseudonymous resident code only (no names, DOB or Medicare numbers).
- Every resident and observation carries data_source ('fictional_demo' or 'real'); triggers stop the
  two from mixing. Intake data never writes into the food-waste `transactions` table.
- Observations are versioned: a correction inserts a new version and marks the old one not current,
  so the original entry is never overwritten.
- Menu items are linked by food_items.id (stable) plus a label snapshot, because
  harbison_menu_schedule is rebuilt on every menu import.
"""
from __future__ import annotations

from datetime import datetime

INTAKE_PERCENTAGES = (0, 25, 50, 75, 100)
COMPONENT_GROUPS = ("protein", "carbohydrate", "vegetables", "soup", "dessert", "drinks", "other")
MEAL_STATUSES = ("served", "refused", "missed", "replacement")
DATA_SOURCES = ("fictional_demo", "real")

INTAKE_SCHEMA = """
CREATE TABLE IF NOT EXISTS intake_residents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_code TEXT NOT NULL UNIQUE,
    facility_id INTEGER NOT NULL,
    service_area_id INTEGER NOT NULL,
    menu_variant TEXT NOT NULL DEFAULT 'Regular',
    room TEXT,
    display_name TEXT,
    data_source TEXT NOT NULL CHECK(data_source IN ('fictional_demo','real')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by INTEGER,
    FOREIGN KEY(facility_id) REFERENCES facilities(id),
    FOREIGN KEY(service_area_id) REFERENCES service_areas(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS intake_meal_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL,
    service_date TEXT NOT NULL,
    meal_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    service_area_id INTEGER NOT NULL,
    menu_variant TEXT,
    menu_week INTEGER,
    meal_status TEXT NOT NULL CHECK(meal_status IN ('served','refused','missed','replacement')),
    missed_reason TEXT,
    replacement_description TEXT,
    staff_observation TEXT CHECK(staff_observation IS NULL OR length(staff_observation) <= 300),
    data_source TEXT NOT NULL CHECK(data_source IN ('fictional_demo','real')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    supersedes_id INTEGER,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0,1)),
    correction_reason TEXT,
    recorded_by INTEGER,
    recorded_at TEXT NOT NULL,
    CHECK(version = 1 OR (supersedes_id IS NOT NULL AND correction_reason IS NOT NULL)),
    FOREIGN KEY(resident_id) REFERENCES intake_residents(id),
    FOREIGN KEY(meal_id) REFERENCES meals(id),
    FOREIGN KEY(facility_id) REFERENCES facilities(id),
    FOREIGN KEY(service_area_id) REFERENCES service_areas(id),
    FOREIGN KEY(supersedes_id) REFERENCES intake_meal_observations(id),
    FOREIGN KEY(recorded_by) REFERENCES users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_intake_obs_current
    ON intake_meal_observations(resident_id, service_date, meal_id) WHERE is_current = 1;
CREATE INDEX IF NOT EXISTS idx_intake_obs_date ON intake_meal_observations(service_date);
CREATE INDEX IF NOT EXISTS idx_intake_obs_resident ON intake_meal_observations(resident_id, service_date);

CREATE TABLE IF NOT EXISTS intake_component_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    component_group TEXT NOT NULL
        CHECK(component_group IN ('protein','carbohydrate','vegetables','soup','dessert','drinks','other')),
    food_item_id INTEGER,
    item_label TEXT NOT NULL,
    observed_status TEXT NOT NULL CHECK(observed_status IN ('observed','not_observed','unknown')),
    intake_pct INTEGER CHECK(intake_pct IS NULL OR intake_pct IN (0,25,50,75,100)),
    served_weight_g REAL CHECK(served_weight_g IS NULL OR served_weight_g >= 0),
    reason_uneaten TEXT,
    reason_other TEXT CHECK(reason_other IS NULL OR length(reason_other) <= 120),
    CHECK((observed_status = 'observed') = (intake_pct IS NOT NULL)),
    FOREIGN KEY(observation_id) REFERENCES intake_meal_observations(id) ON DELETE CASCADE,
    FOREIGN KEY(food_item_id) REFERENCES food_items(id)
);

CREATE INDEX IF NOT EXISTS idx_intake_comp_obs ON intake_component_observations(observation_id);
CREATE INDEX IF NOT EXISTS idx_intake_comp_food ON intake_component_observations(food_item_id);

CREATE TABLE IF NOT EXISTS intake_meal_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL,
    service_date TEXT NOT NULL,
    meal_id INTEGER NOT NULL,
    item_label TEXT NOT NULL CHECK(length(item_label) <= 80),
    component_group TEXT NOT NULL
        CHECK(component_group IN ('protein','carbohydrate','vegetables','soup','dessert','drinks','other')),
    food_item_id INTEGER,
    data_source TEXT NOT NULL CHECK(data_source IN ('fictional_demo','real')),
    ordered_by INTEGER,
    ordered_at TEXT NOT NULL,
    UNIQUE(resident_id, service_date, meal_id, item_label),
    FOREIGN KEY(resident_id) REFERENCES intake_residents(id),
    FOREIGN KEY(meal_id) REFERENCES meals(id),
    FOREIGN KEY(food_item_id) REFERENCES food_items(id),
    FOREIGN KEY(ordered_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_intake_orders_day ON intake_meal_orders(service_date, meal_id);

-- Keep fictional and real records strictly separate at the database level.
CREATE TRIGGER IF NOT EXISTS trg_intake_obs_source
BEFORE INSERT ON intake_meal_observations
WHEN NEW.data_source <> (SELECT data_source FROM intake_residents WHERE id = NEW.resident_id)
BEGIN
    SELECT RAISE(ABORT, 'Observation data_source must match the resident data_source');
END;

CREATE TRIGGER IF NOT EXISTS trg_intake_order_source
BEFORE INSERT ON intake_meal_orders
WHEN NEW.data_source <> (SELECT data_source FROM intake_residents WHERE id = NEW.resident_id)
BEGIN
    SELECT RAISE(ABORT, 'Order data_source must match the resident data_source');
END;

-- History is append-only: observations cannot be edited in place,
-- except for flipping is_current when a correction supersedes a version.
CREATE TRIGGER IF NOT EXISTS trg_intake_obs_immutable
BEFORE UPDATE ON intake_meal_observations
WHEN NOT (OLD.is_current = 1 AND NEW.is_current = 0)
     OR NEW.resident_id <> OLD.resident_id OR NEW.service_date <> OLD.service_date
     OR NEW.meal_id <> OLD.meal_id OR NEW.meal_status <> OLD.meal_status
     OR NEW.version <> OLD.version OR NEW.data_source <> OLD.data_source
     OR IFNULL(NEW.staff_observation,'') <> IFNULL(OLD.staff_observation,'')
BEGIN
    SELECT RAISE(ABORT, 'Intake observations are append-only; record a correction instead');
END;

CREATE TRIGGER IF NOT EXISTS trg_intake_comp_immutable
BEFORE UPDATE ON intake_component_observations
BEGIN
    SELECT RAISE(ABORT, 'Component observations are append-only; record a correction instead');
END;
"""


def seed_intake_defaults(c):
    """Small additive upgrades for databases created by earlier versions."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(intake_residents)").fetchall()}
    if "room" not in cols:
        c.execute("ALTER TABLE intake_residents ADD COLUMN room TEXT")
    if "display_name" not in cols:  # synthetic data names only; real residents stay code-only
        c.execute("ALTER TABLE intake_residents ADD COLUMN display_name TEXT")
    comp_cols = {r[1] for r in c.execute("PRAGMA table_info(intake_component_observations)").fetchall()}
    if "served_weight_g" not in comp_cols:
        c.execute("ALTER TABLE intake_component_observations ADD COLUMN served_weight_g REAL")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('intake_real_records_enabled','0')")
