import json

import pytest
from fastapi.testclient import TestClient

from portal.api import create_app
from portal.data import PAGES, Portal
from portal.export import export_site


@pytest.fixture(scope="module")
def warehouse(runs):
    data, first, second = runs
    assert first.success and second.success
    return data / "warehouse.duckdb"


@pytest.fixture(scope="module")
def portal(warehouse):
    p = Portal(warehouse)
    yield p
    p.close()


def test_every_page_is_json(portal):
    for page in PAGES:
        json.dumps(getattr(portal, page)())  # raises on dates, decimals, ...


def test_figures_agree_across_pages(portal):
    projects = portal.projects()
    k = portal.overview()["kpis"]
    in_flight = [p for p in projects if p["status"] in ("active", "to_report", "not_started", "on_hold")]
    assert k["in_flight"] == len(in_flight) == k["in_flight_front"] + k["in_flight_middle"]
    assert k["in_flight"] == len(portal.timeline()["projects"])
    risks = portal.risks()["findings"]
    assert k["red_flags"] == len({r["project_id"] for r in risks if r["risk_level"] == "high"})
    assert k["pending_requests"] == len(portal.approvals()["pending"])
    # the main risk on the project list is the one the risk mart marks as main
    main = {r["project_id"]: r["risk_level"] for r in risks if r["is_main_risk"]}
    assert all(p["risk_level"] == main.get(p["id"]) for p in projects)


def test_project_detail(portal):
    pid = next(p["id"] for p in portal.projects() if p["status"] == "active")
    d = portal.project(pid)
    assert d["project"]["project_id"] == pid
    assert d["history"] and d["history"][-1]["valid_to"] is None  # SCD2: last version is open
    assert all(isinstance(u["risks"], list) for u in d["updates"])
    assert portal.project(10**9) is None


def test_biweekly_lists_the_next_meeting_per_track(portal):
    tracks = portal.biweekly()["tracks"]
    assert [t["track"] for t in tracks] == ["front", "middle"]
    for t in tracks:
        assert t["upcoming"] >= portal.as_of.isoformat()
        assert all(m["meeting_date"] < t["upcoming"] for m in t["history"])


def test_api(warehouse):
    client = TestClient(create_app(warehouse))
    assert client.get("/api/overview.json").json()["kpis"]["in_flight"] > 0
    pid = client.get("/api/projects.json").json()[0]["id"]
    assert client.get(f"/api/projects/{pid}.json").status_code == 200
    assert client.get("/api/projects/999999999.json").status_code == 404
    assert client.get("/api/nope.json").status_code == 404
    assert "<title>" in client.get("/").text
    assert client.get("/app.js").status_code == 200


def test_api_without_warehouse(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.duckdb"))
    assert client.get("/api/meta.json").status_code == 503


def test_static_export(warehouse, tmp_path):
    out = tmp_path / "site"
    r = export_site(warehouse, out)
    assert (out / "index.html").exists() and (out / "app.js").exists() and (out / ".nojekyll").exists()
    for page in PAGES:
        assert (out / "api" / f"{page}.json").exists()
    assert len(list((out / "api" / "projects").glob("*.json"))) == r["projects"] > 100
    # the export holds exactly what the live API serves
    client = TestClient(create_app(warehouse))
    exported = json.loads((out / "api" / "risks.json").read_text())
    assert exported == client.get("/api/risks.json").json()


def test_portal_does_not_lock_the_warehouse(warehouse, tmp_path):
    """The API opens a connection per request, so a pipeline run can write in between."""
    import shutil

    import duckdb

    copy = tmp_path / "warehouse.duckdb"  # a copy: this module's `portal` fixture keeps the original open
    shutil.copy(warehouse, copy)
    client = TestClient(create_app(copy))
    assert client.get("/api/overview.json").status_code == 200
    duckdb.connect(str(copy)).close()  # a writer can open it straight after a request
