import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

import src.db as db
from src.intake import (
    ComponentEntry, MealEntry, add_order, component_group_for, correct_observation, create_resident,
    current_observation, day_overview, meal_level_frame, meal_results, observation_history, orders_for,
    save_observation,
)
from src.synthetic_intake import generate_synthetic_resident_data

DAY = date.today() - timedelta(days=3)


def _resident(code="DEMO-T-001", source="fictional_demo", area=1):
    return create_resident(code, 1, area, "Regular", source, None)


def _served(rid, day=DAY, meal="Lunch", pcts=(100, 50, 0), extra=()):
    labels = ["Roast Chicken", "Mashed Potato", "Steamed Broccoli"]
    comps = [ComponentEntry("protein", labels[i % 3], "observed", p, served_weight_g=180) for i, p in enumerate(pcts)]
    comps += list(extra)
    return MealEntry(rid, day, meal, "served", comps)


# ---------------------------------------------------------------- migration

def test_users_migration_adds_care_role_and_keeps_users(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','manager','kitchen','dietitian')),
            password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            user_id INTEGER, action TEXT NOT NULL, details TEXT, FOREIGN KEY(user_id) REFERENCES users(id));
        INSERT INTO users VALUES (1,'admin','Admin','admin','h',1,'2026-01-01');
        INSERT INTO audit_log VALUES (1,'2026-01-01',1,'LOGIN','');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    db.init_db()  # idempotent
    assert "'care'" in db.fetchone("SELECT sql FROM sqlite_master WHERE name='users'")["sql"]
    assert db.fetchone("SELECT username FROM users WHERE id=1")["username"] == "admin"
    assert db.fetchone("SELECT user_id FROM audit_log WHERE id=1")["user_id"] == 1
    assert len(list(tmp_path.glob("food_waste_before_care_role_*.db"))) == 1
    with db.connection() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        c.execute("INSERT INTO users(username,display_name,role,password_hash,created_at) "
                  "VALUES('n','N','care','h','x')")


# ---------------------------------------------------------------- component mapping

@pytest.mark.parametrize("comp,cat,label,expected", [
    ("Main", "Main Meals", "Roast Chicken", "protein"),
    ("Side", "Vegetables and Sides", "Mashed Potato", "carbohydrate"),
    ("Side", "Vegetables and Sides", "Steamed Broccoli", "vegetables"),
    ("Dessert", "Desserts", "Apple Crumble", "dessert"),
    ("Main", "Soup", "Pumpkin Soup", "soup"),
    ("Main", "Breakfast", "Porridge with Banana", "carbohydrate"),
    ("Main", "Breakfast", "Scrambled Eggs", "protein"),
    ("Beverage", "Drinks", "Orange Juice", "drinks"),
])
def test_component_group_for(comp, cat, label, expected):
    assert component_group_for(comp, cat, label) == expected


# ---------------------------------------------------------------- recording rules

def test_not_observed_and_unknown_are_not_zero(temp_db):
    rid = _resident()
    save_observation(_served(rid, pcts=(100,), extra=[
        ComponentEntry("vegetables", "Steamed Broccoli", "not_observed", served_weight_g=80),
        ComponentEntry("drinks", "Drink with meal", "unknown", served_weight_g=200),
    ]), None)
    meals = meal_level_frame("fictional_demo")
    assert meals.meal_intake_pct.iloc[0] == 100  # unobserved items are excluded, not averaged as 0
    assert meals.unobserved_components.iloc[0] == 2


def test_validation_rejects_bad_entries(temp_db):
    rid = _resident()
    with pytest.raises(ValueError):
        save_observation(MealEntry(rid, DAY, "Lunch", "served",
                                   [ComponentEntry("protein", "Roast Chicken", "observed", None)]), None)
    with pytest.raises(ValueError):
        save_observation(MealEntry(rid, DAY, "Lunch", "served",
                                   [ComponentEntry("protein", "Roast Chicken", "not_observed", 50)]), None)
    with pytest.raises(ValueError):
        save_observation(MealEntry(rid, DAY, "Lunch", "served",
                                   [ComponentEntry("protein", "Roast Chicken", "observed", 60)]), None)
    with pytest.raises(ValueError):
        save_observation(MealEntry(rid, DAY, "Lunch", "missed"), None)  # reason required
    with pytest.raises(ValueError):
        save_observation(_served(rid, day=date.today() + timedelta(days=1)), None)


def test_refused_counts_as_zero_and_missed_is_excluded(temp_db):
    rid = _resident()
    save_observation(MealEntry(rid, DAY, "Breakfast", "refused"), None)
    save_observation(MealEntry(rid, DAY, "Lunch", "missed", missed_reason="In hospital"), None)
    save_observation(_served(rid, meal="Dinner", pcts=(100, 100)), None)
    meals = meal_level_frame("fictional_demo").set_index("meal_service")
    assert meals.loc["Breakfast", "meal_intake_pct"] == 0
    assert pd.isna(meals.loc["Lunch", "meal_intake_pct"])
    assert meals.meal_intake_pct.mean() == 50


def test_duplicate_meal_is_blocked(temp_db):
    rid = _resident()
    save_observation(_served(rid), None)
    with pytest.raises(FileExistsError):
        save_observation(_served(rid), None)


# ---------------------------------------------------------------- corrections and audit

def test_correction_keeps_original_version(temp_db):
    rid = _resident()
    first = save_observation(_served(rid, pcts=(25,)), None)
    second = correct_observation(first, _served(rid, pcts=(75,)), "Entered against wrong resident row", None)
    current = current_observation(rid, DAY, "Lunch")
    assert current["id"] == second and current["version"] == 2
    history = observation_history(second)
    assert [v["version"] for v in history] == [2, 1]
    assert history[1]["components"][0]["intake_pct"] == 25  # original preserved
    assert meal_level_frame("fictional_demo").meal_intake_pct.tolist() == [75]
    assert db.fetchone("SELECT COUNT(*) n FROM audit_log WHERE action='INTAKE_CORRECTION'")["n"] == 1
    with pytest.raises(ValueError):
        correct_observation(first, _served(rid, pcts=(50,)), "again", None)  # superseded version
    with pytest.raises(ValueError):
        correct_observation(second, _served(rid, pcts=(50,)), "  ", None)  # reason required


def test_history_rows_cannot_be_edited_in_place(temp_db):
    rid = _resident()
    obs = save_observation(_served(rid), None)
    with db.connection() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE intake_meal_observations SET staff_observation='changed' WHERE id=?", (obs,))
    with db.connection() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE intake_component_observations SET intake_pct=100 WHERE observation_id=?", (obs,))


# ---------------------------------------------------------------- data separation and safety

def test_real_records_blocked_until_enabled(temp_db):
    with pytest.raises(PermissionError):
        _resident("R-0001", source="real")
    db.set_setting("intake_real_records_enabled", "1")
    real = _resident("R-0001", source="real")
    save_observation(_served(real), None)
    assert len(meal_level_frame("real")) == 1
    assert meal_level_frame("fictional_demo").empty


def test_database_rejects_mixed_data_sources(temp_db):
    rid = _resident()
    with db.connection() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute(
            """INSERT INTO intake_meal_observations(resident_id,service_date,meal_id,facility_id,service_area_id,
                   meal_status,data_source,recorded_at) VALUES(?,?,3,1,1,'refused','real','x')""",
            (rid, DAY.isoformat()),
        )


def test_resident_codes_reject_names(temp_db):
    with pytest.raises(ValueError):
        _resident("Mary Smith")


def _waste_rows():
    return db.fetchall("SELECT t.*, fi.name food FROM transactions t JOIN food_items fi ON fi.id=t.food_item_id "
                       "WHERE intake_observation_id IS NOT NULL ORDER BY fi.name")


def test_saved_meal_keeps_resident_weights_separate_from_measured_food_waste(temp_db):
    rid = _resident()
    fid = db.fetchone("SELECT id FROM food_items WHERE name='Roast Chicken'")["id"]
    obs = save_observation(MealEntry(rid, DAY, "Lunch", "served", [
        ComponentEntry("protein", "Roast Chicken", "observed", 25, fid, served_weight_g=200, reason_uneaten="Poor appetite"),
        ComponentEntry("soup", "Soup", "observed", 100, served_weight_g=250),
    ]), None)
    saved = current_observation(rid, DAY, "Lunch")
    assert saved["components"][0]["served_weight_g"] == 200
    assert saved["components"][0]["intake_pct"] == 25
    assert db.fetchone("SELECT COUNT(*) n FROM transactions WHERE intake_observation_id=?", (obs,))["n"] == 0

def test_refused_and_missed_meals_do_not_create_measured_waste(temp_db):
    rid = _resident()
    add_order(rid, DAY, "Dinner", "Beef Casserole", "protein", None, None)
    save_observation(MealEntry(rid, DAY, "Dinner", "refused"), None)
    save_observation(MealEntry(rid, DAY, "Lunch", "missed", missed_reason="In hospital"), None)
    assert _waste_rows() == []


def test_correction_updates_intake_history_without_creating_waste_rows(temp_db):
    rid = _resident()
    first = save_observation(_served(rid, pcts=(0,)), None)
    second = correct_observation(first, _served(rid, pcts=(75,)), "Wrong tray", None)
    assert _waste_rows() == []
    assert current_observation(rid, DAY, "Lunch")["id"] == second


# ---------------------------------------------------------------- orders

def test_orders_and_day_overview(temp_db):
    rid = _resident()
    add_order(rid, DAY, "Lunch", "Roast Chicken", "protein", None, None)
    add_order(rid, DAY, "Lunch", "Soup", "soup", None, None)
    add_order(rid, DAY, "Lunch", "Soup", "soup", None, None)  # duplicate ignored
    add_order(rid, DAY, "Afternoon Tea", "Ice cream", "dessert", None, None)
    assert [o["item_label"] for o in orders_for("fictional_demo", DAY, "Lunch")[rid]] == ["Soup", "Roast Chicken"]
    with pytest.raises(ValueError):
        add_order(rid, DAY, "Lunch", "  ", "soup", None, None)

    before = day_overview("fictional_demo", DAY).iloc[0]
    assert before["Lunch"] == "Soup, Roast Chicken" and before["Afternoon tea"] == "Ice cream"
    save_observation(MealEntry(rid, DAY, "Lunch", "served", [
        ComponentEntry("soup", "Soup", "observed", 100),
        ComponentEntry("protein", "Roast Chicken", "observed", 50),
    ]), None)
    save_observation(MealEntry(rid, DAY, "Afternoon Tea", "refused"), None)
    after = day_overview("fictional_demo", DAY).iloc[0]
    assert after["Lunch"] == "✓ 75% eaten" and after["Afternoon tea"] == "Refused"
    assert meal_results("fictional_demo", DAY, "Lunch")[rid]["avg_pct"] == 75


def test_orders_cannot_cross_data_sources(temp_db):
    rid = _resident()
    with db.connection() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("""INSERT INTO intake_meal_orders(resident_id,service_date,meal_id,item_label,component_group,
                         data_source,ordered_at) VALUES(?,?,3,'Jelly','dessert','real','x')""", (rid, DAY.isoformat()))


def test_demo_generator_orders_today_but_leaves_it_unrecorded(temp_db):
    today = date.today()
    counts = generate_synthetic_resident_data(today - timedelta(days=3), today - timedelta(days=1), residents_per_area=3)
    assert counts["residents"] == 6
    lunch_today = orders_for("fictional_demo", today, "Lunch")
    assert len(lunch_today) == 6
    labels = {o["item_label"] for items in lunch_today.values() for o in items}
    assert "Roast Chicken" in labels
    tea = {o["item_label"] for items in orders_for("fictional_demo", today, "Afternoon Tea").values() for o in items}
    from src.resident_choices import CHOICE_BY_NAME
    assert tea and all(t in CHOICE_BY_NAME for t in tea)  # tea-time items come from the resident choices
    assert meal_results("fictional_demo", today, "Lunch") == {}
    assert len(meal_results("fictional_demo", today - timedelta(days=1), "Lunch")) >= 4
    rooms = [r["room"] for r in db.fetchall("SELECT room FROM intake_residents ORDER BY id")]
    assert rooms == ["101", "102", "103", "201", "202", "203"]
    sent = db.fetchone("SELECT COUNT(*) n FROM transactions WHERE intake_observation_id IS NOT NULL")["n"]
    assert sent == 0
    assert db.fetchone("SELECT COUNT(*) n FROM transactions WHERE service_date=?", (today.isoformat(),))["n"] == 0
