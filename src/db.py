from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DB_PATH = APP_DIR / "data" / "food_waste_v2.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','manager','kitchen','dietitian','care')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS service_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(facility_id, name),
    FOREIGN KEY(facility_id) REFERENCES facilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS food_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS food_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category_id INTEGER,
    manual_cost_per_kg REAL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(category_id) REFERENCES food_categories(id)
);

CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    base_unit TEXT NOT NULL CHECK(base_unit IN ('kg','L','each')),
    supplier TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ingredient_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_id INTEGER NOT NULL,
    effective_date TEXT NOT NULL,
    pack_quantity REAL NOT NULL CHECK(pack_quantity > 0),
    pack_unit TEXT NOT NULL CHECK(pack_unit IN ('kg','L','each')),
    purchase_price REAL NOT NULL CHECK(purchase_price >= 0),
    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
    recorded_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
    FOREIGN KEY(recorded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food_item_id INTEGER NOT NULL UNIQUE,
    yield_kg REAL NOT NULL CHECK(yield_kg > 0),
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(food_item_id) REFERENCES food_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    quantity REAL NOT NULL CHECK(quantity >= 0),
    unit TEXT NOT NULL CHECK(unit IN ('kg','L','each')),
    UNIQUE(recipe_id, ingredient_id),
    FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
    FOREIGN KEY(ingredient_id) REFERENCES ingredients(id)
);

CREATE TABLE IF NOT EXISTS menu_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    cycle_start_date TEXT NOT NULL,
    cycle_weeks INTEGER NOT NULL DEFAULT 4
);

CREATE TABLE IF NOT EXISTS menu_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number INTEGER NOT NULL CHECK(week_number BETWEEN 1 AND 4),
    day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
    meal_id INTEGER NOT NULL,
    food_item_id INTEGER NOT NULL,
    UNIQUE(week_number, day_of_week, meal_id, food_item_id),
    FOREIGN KEY(meal_id) REFERENCES meals(id),
    FOREIGN KEY(food_item_id) REFERENCES food_items(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    service_date TEXT NOT NULL,
    facility_id INTEGER NOT NULL,
    service_area_id INTEGER NOT NULL,
    meal_id INTEGER NOT NULL,
    food_item_id INTEGER NOT NULL,
    waste_type TEXT NOT NULL CHECK(waste_type IN ('Production Waste','Plate Waste')),
    prepared_kg REAL,
    served_kg REAL,
    waste_kg REAL NOT NULL CHECK(waste_kg >= 0),
    waste_percentage REAL,
    cost_per_kg_snapshot REAL,
    waste_cost REAL,
    waste_reason TEXT,
    resident_count INTEGER,
    notes TEXT,
    recorded_by INTEGER,
    is_demo INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(facility_id) REFERENCES facilities(id),
    FOREIGN KEY(service_area_id) REFERENCES service_areas(id),
    FOREIGN KEY(meal_id) REFERENCES meals(id),
    FOREIGN KEY(food_item_id) REFERENCES food_items(id),
    FOREIGN KEY(recorded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Sponsor-provided reference data is kept separate from operational waste data.
-- These tables can be safely rebuilt from the structured import files.

CREATE TABLE IF NOT EXISTS supplier_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    product_name TEXT NOT NULL UNIQUE,
    pfd_price REAL,
    superior_foods_price REAL,
    sfd_price REAL,
    source_page INTEGER,
    source_document TEXT,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sponsor_recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food_item_id INTEGER NOT NULL UNIQUE,
    recipe_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    texture TEXT,
    serves INTEGER NOT NULL,
    serving_size_g REAL NOT NULL,
    yield_loss_pct REAL,
    allergens TEXT,
    dietary_notes TEXT,
    source_page INTEGER,
    source_document TEXT,
    imported_at TEXT NOT NULL,
    FOREIGN KEY(food_item_id) REFERENCES food_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sponsor_recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sponsor_recipe_id INTEGER NOT NULL,
    line_order INTEGER NOT NULL,
    quantity REAL,
    unit TEXT,
    ingredient_name TEXT NOT NULL,
    source_document TEXT,
    UNIQUE(sponsor_recipe_id, line_order),
    FOREIGN KEY(sponsor_recipe_id) REFERENCES sponsor_recipes(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS harbison_menu_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_variant TEXT NOT NULL,
    week_number INTEGER NOT NULL CHECK(week_number BETWEEN 1 AND 4),
    day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
    day_name TEXT,
    meal_service TEXT NOT NULL,
    component TEXT NOT NULL,
    menu_label TEXT NOT NULL,
    food_item_id INTEGER NOT NULL,
    linked_recipe_name TEXT,
    linked_recipe_food_item_id INTEGER,
    category TEXT,
    source_sheet TEXT,
    source_document TEXT,
    imported_at TEXT NOT NULL,
    UNIQUE(menu_variant,week_number,day_of_week,meal_service,component,menu_label),
    FOREIGN KEY(food_item_id) REFERENCES food_items(id),
    FOREIGN KEY(linked_recipe_food_item_id) REFERENCES food_items(id)
);

CREATE TABLE IF NOT EXISTS menu_item_recipe_links (
    menu_food_item_id INTEGER PRIMARY KEY,
    recipe_food_item_id INTEGER NOT NULL,
    FOREIGN KEY(menu_food_item_id) REFERENCES food_items(id) ON DELETE CASCADE,
    FOREIGN KEY(recipe_food_item_id) REFERENCES food_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthetic_generation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    seed INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    resident_min INTEGER NOT NULL,
    resident_max INTEGER NOT NULL,
    location_count INTEGER NOT NULL,
    menu_rows_used INTEGER NOT NULL DEFAULT 0,
    transactions_created INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(service_date);
CREATE INDEX IF NOT EXISTS idx_tx_food ON transactions(food_item_id);
CREATE INDEX IF NOT EXISTS idx_price_effective ON ingredient_price_history(ingredient_id,effective_date);
"""


def _migrate_users_role_constraint():
    """Rebuild users so its role CHECK allows 'care' (Nurse / Care Worker).

    SQLite cannot alter a CHECK constraint, so this follows the documented table-rebuild
    procedure: backup, foreign keys off, one transaction, foreign_key_check before commit.
    """
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not row or "'care'" in row[0]:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = sqlite3.connect(DB_PATH.with_name(f"food_waste_before_care_role_{stamp}.db"))
        conn.backup(backup)
        backup.close()
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','manager','kitchen','dietitian','care')),
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """INSERT INTO users_new(id,username,display_name,role,password_hash,active,created_at)
                   SELECT id,username,display_name,role,password_hash,active,created_at FROM users"""
            )
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_new RENAME TO users")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Foreign key check failed while migrating users table.")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
    finally:
        conn.close()


def init_db():
    from .intake_db import INTAKE_SCHEMA, seed_intake_defaults

    _migrate_users_role_constraint()
    with connection() as c:
        c.executescript(SCHEMA)
        c.executescript(INTAKE_SCHEMA)
        seed_intake_defaults(c)
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('plate_waste_kpi','20')")
        c.execute(
            "INSERT OR IGNORE INTO menu_settings(id,cycle_start_date,cycle_weeks) VALUES(1,'2026-08-03',4)"
        )
        tx_cols = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
        if "menu_variant" not in tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN menu_variant TEXT")
        if "menu_component" not in tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN menu_component TEXT")
        if "synthetic_run_id" not in tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN synthetic_run_id INTEGER")
        if "intake_observation_id" not in tx_cols:
            # Links plate waste sent from Plate Waste Management back to the nurse's meal record.
            c.execute("ALTER TABLE transactions ADD COLUMN intake_observation_id INTEGER")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_synthetic_run ON transactions(synthetic_run_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_intake_obs ON transactions(intake_observation_id)")


def fetchall(sql: str, params=()):
    with connection() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def fetchone(sql: str, params=()):
    with connection() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params=()):
    with connection() as c:
        cur = c.execute(sql, params)
        return int(cur.lastrowid or 0)


def log_action(user_id: int | None, action: str, details: str = ""):
    execute(
        "INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), user_id, action, details),
    )


def setting(key: str, default: str | None = None):
    r = fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str):
    execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
