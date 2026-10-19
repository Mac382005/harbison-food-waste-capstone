from pathlib import Path

import pytest

import src.db as db
from src.locations import add_dining_area, add_site


def test_add_site_with_dining_areas(temp_db):
    fid = add_site("  Harbison Site 9 ", ["Dining Area 1", " Dining Area 2", "", "Dining Area 1"], None)
    assert db.fetchone("SELECT name FROM facilities WHERE id=?", (fid,))["name"] == "Harbison Site 9"
    areas = [r["name"] for r in db.fetchall("SELECT name FROM service_areas WHERE facility_id=? ORDER BY id", (fid,))]
    assert areas == ["Dining Area 1", "Dining Area 2"]  # blanks and duplicates dropped
    with pytest.raises(ValueError, match="already exists"):
        add_site("harbison site 9", ["A"], None)
    with pytest.raises(ValueError, match="at least one dining area"):
        add_site("Harbison Site 10", [" ", ""], None)
    add_dining_area(fid, "Dining Area 3", None)
    with pytest.raises(ValueError, match="already exists"):
        add_dining_area(fid, "dining area 3", None)
    assert db.fetchone("SELECT COUNT(*) n FROM audit_log WHERE action IN ('ADD_FACILITY','ADD_SERVICE_AREA')")["n"] == 2


def test_delete_site_removes_its_records_and_keeps_others(temp_db):
    from src.intake import create_resident
    from src.locations import delete_site, site_usage

    keep = db.fetchone("SELECT id FROM facilities WHERE name='Test Facility'")["id"]
    create_resident("KEEP-1", keep, 1, "Regular", "fictional_demo", None)
    fid = add_site("Harbison Site 9", ["Dining Area 1"], None)
    area = db.fetchone("SELECT id FROM service_areas WHERE facility_id=?", (fid,))["id"]
    create_resident("GONE-1", fid, area, "Regular", "fictional_demo", None)
    triggers = db.fetchone("SELECT COUNT(*) n FROM sqlite_master WHERE type='trigger'")["n"]

    assert site_usage(fid)["Residents"] == 1
    with pytest.raises(ValueError, match="exactly"):
        delete_site(fid, "Harbison Site", None)
    backup = delete_site(fid, " harbison site 9 ", None)

    assert Path(backup).exists()
    assert db.fetchone("SELECT COUNT(*) n FROM facilities WHERE id=?", (fid,))["n"] == 0
    assert [r["resident_code"] for r in db.fetchall("SELECT resident_code FROM intake_residents")] == ["KEEP-1"]
    assert db.fetchone("SELECT COUNT(*) n FROM sqlite_master WHERE type='trigger'")["n"] == triggers
    with pytest.raises(ValueError, match="only site"):
        delete_site(keep, "Test Facility", None)
