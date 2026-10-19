"""Add sites (facilities) and dining areas. Shared by Food Waste Management and Resident Meal & Consumption Records."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from . import db
from .db import connection


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip()


def add_site(name: str, dining_areas: list[str], user_id: int | None) -> int:
    """Create a site together with its dining areas; returns the new facility id."""
    name = _clean(name)
    areas = list(dict.fromkeys(a for a in (_clean(x) for x in dining_areas) if a))
    if not 2 <= len(name) <= 60:
        raise ValueError("Site name must be 2-60 characters.")
    if not areas:
        raise ValueError("Add at least one dining area, so residents have somewhere to go.")
    if any(len(a) > 60 for a in areas):
        raise ValueError("Dining area names must be 60 characters or fewer.")
    with connection() as c:
        if c.execute("SELECT 1 FROM facilities WHERE lower(name)=lower(?)", (name,)).fetchone():
            raise ValueError(f"A site called '{name}' already exists.")
        fid = int(c.execute("INSERT INTO facilities(name,active) VALUES(?,1)", (name,)).lastrowid)
        for area in areas:
            c.execute("INSERT INTO service_areas(facility_id,name,active) VALUES(?,?,1)", (fid, area))
        c.execute("INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), user_id, "ADD_FACILITY",
                   f"{name} ({', '.join(areas)})"))
    return fid


def add_dining_area(facility_id: int, name: str, user_id: int | None) -> None:
    name = _clean(name)
    if not 1 <= len(name) <= 60:
        raise ValueError("Dining area name must be 1-60 characters.")
    with connection() as c:
        site = c.execute("SELECT name FROM facilities WHERE id=?", (facility_id,)).fetchone()
        if site is None:
            raise ValueError("Site not found.")
        if c.execute("SELECT 1 FROM service_areas WHERE facility_id=? AND lower(name)=lower(?)",
                     (facility_id, name)).fetchone():
            raise ValueError(f"'{name}' already exists at {site[0]}.")
        c.execute("INSERT INTO service_areas(facility_id,name,active) VALUES(?,?,1)", (facility_id, name))
        c.execute("INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), user_id, "ADD_SERVICE_AREA", f"{site[0]}: {name}"))


def _site_scope(fid: int) -> dict[str, str]:
    residents = f"(SELECT id FROM intake_residents WHERE facility_id={fid})"
    return {
        "residents": residents,
        "observations": f"(SELECT id FROM intake_meal_observations WHERE facility_id={fid} "
                        f"OR resident_id IN {residents})",
        "areas": f"(SELECT id FROM service_areas WHERE facility_id={fid})",
    }


def site_usage(facility_id: int) -> dict[str, int]:
    """What deleting a site would remove."""
    fid = int(facility_id)
    q = _site_scope(fid)
    with connection() as c:
        def count(sql):
            return int(c.execute(sql).fetchone()[0])
        return {
            "Dining areas": count(f"SELECT COUNT(*) FROM service_areas WHERE facility_id={fid}"),
            "Residents": count(f"SELECT COUNT(*) FROM intake_residents WHERE facility_id={fid}"),
            "Meal records": count(f"SELECT COUNT(*) FROM intake_meal_observations WHERE id IN {q['observations']}"),
            "Food waste records": count(
                f"SELECT COUNT(*) FROM transactions WHERE facility_id={fid} OR service_area_id IN {q['areas']} "
                f"OR intake_observation_id IN {q['observations']}"),
        }


def delete_site(facility_id: int, typed_name: str, user_id: int | None) -> str:
    """Permanently delete a site with its dining areas, residents, orders, meal and waste records.

    The typed name must match the site name. The database is backed up first (returns the backup path)
    and everything runs in one transaction, so a failure changes nothing.
    """
    fid = int(facility_id)
    with connection() as c:
        site = c.execute("SELECT name FROM facilities WHERE id=?", (fid,)).fetchone()
        site_count = c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    if site is None:
        raise ValueError("Site not found.")
    if _clean(typed_name).lower() != site[0].lower():
        raise ValueError(f"Type the site name exactly ('{site[0]}') to confirm.")
    if site_count <= 1:
        raise ValueError("You can't delete the only site.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db.DB_PATH.with_name(f"{db.DB_PATH.stem}.backup_before_delete_site_{fid}_{stamp}.db")
    src, dst = sqlite3.connect(db.DB_PATH), sqlite3.connect(backup)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    q = _site_scope(fid)
    statements = [
        f"DELETE FROM transactions WHERE facility_id={fid} OR service_area_id IN {q['areas']} "
        f"OR intake_observation_id IN {q['observations']}",
        f"DELETE FROM intake_component_observations WHERE observation_id IN {q['observations']}",
        f"DELETE FROM intake_meal_observations WHERE id IN {q['observations']}",
        f"DELETE FROM intake_review_events WHERE review_id IN "
        f"(SELECT id FROM intake_clinical_reviews WHERE resident_id IN {q['residents']})",
        f"DELETE FROM intake_clinical_reviews WHERE resident_id IN {q['residents']}",
        f"DELETE FROM intake_meal_orders WHERE resident_id IN {q['residents']}",
        f"DELETE FROM intake_residents WHERE facility_id={fid}",
        f"DELETE FROM service_areas WHERE facility_id={fid}",
        f"DELETE FROM facilities WHERE id={fid}",
    ]
    c = sqlite3.connect(db.DB_PATH, timeout=30, isolation_level=None)
    try:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("BEGIN IMMEDIATE")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # The append-only triggers block deletes, so lift them inside this transaction only.
        triggers = c.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for name, _ in triggers:
            c.execute(f'DROP TRIGGER "{name}"')
        for sql in statements:
            if sql.split()[2] in tables:
                c.execute(sql)
        for _, sql in triggers:
            c.execute(sql)
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Linked records would be left behind, so nothing was deleted.")
        c.execute("INSERT INTO audit_log(created_at,user_id,action,details) VALUES(?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), user_id, "DELETE_FACILITY",
                   f"{site[0]} (backup {backup.name})"))
        c.execute("COMMIT")
    except Exception:
        if c.in_transaction:
            c.execute("ROLLBACK")
        raise
    finally:
        c.close()
    return str(backup)
