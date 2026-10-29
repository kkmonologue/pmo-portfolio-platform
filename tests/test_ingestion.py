import datetime as dt
import os
import sqlite3

import duckdb
import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine

from ingestion.__main__ import run
from ingestion.app_db import TABLES
from ingestion.tracker import parse_sheet
from simulator.engine import Simulation
from simulator.excel_export import write_week

os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")


def _simulate(data_dir, until, excel_from=None):
    eng = create_engine(f"sqlite:///{data_dir / 'source.db'}")
    sim = Simulation(eng, 11, data_dir)
    sim.bootstrap(dt.date(2024, 7, 1))
    sim.run_until(until, excel_from)
    sim.save()
    for monday, snap in sim.weekly_snapshots:
        write_week(data_dir / "excel", monday, snap, 11)


def _counts_match(data_dir):
    src = sqlite3.connect(data_dir / "source.db")
    with duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=True) as wh:
        for t in TABLES:
            assert src.execute(f"select count(*) from {t}").fetchone()[0] == wh.execute(f"select count(*) from raw.{t}").fetchone()[0], t


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    d = tmp_path_factory.mktemp("ing")
    _simulate(d, dt.date(2025, 5, 31), excel_from=dt.date(2025, 5, 12))
    first = run(f"sqlite:///{d / 'source.db'}", d / "warehouse.duckdb", d / "excel")
    return d, first


def test_full_load_matches_source(loaded):
    d, first = loaded
    _counts_match(d)
    assert first["projects"] > 0 and first["tracker_rows"] > 0


def test_rerun_without_changes_loads_nothing(loaded):
    d, _ = loaded
    again = run(f"sqlite:///{d / 'source.db'}", d / "warehouse.duckdb", d / "excel")
    assert sum(again.values()) == 0


def test_incremental_load_only_brings_changes(loaded):
    d, _ = loaded
    src = sqlite3.connect(d / "source.db")
    before_updates = src.execute("select count(*) from status_updates").fetchone()[0]
    _simulate(d, dt.date(2025, 6, 14), excel_from=dt.date(2025, 6, 1))
    new_updates = src.execute("select count(*) from status_updates").fetchone()[0] - before_updates
    changed_projects = src.execute("select count(*) from projects where updated_at >= '2025-06-01'").fetchone()[0]
    inc = run(f"sqlite:///{d / 'source.db'}", d / "warehouse.duckdb", d / "excel")
    assert inc.get("teams", 0) == 0  # nothing changed there
    assert inc["status_updates"] == new_updates
    assert 0 < inc["projects"] <= changed_projects
    assert inc["tracker_rows"] > 0  # the new weekly workbooks
    _counts_match(d)
    with duckdb.connect(str(d / "warehouse.duckdb"), read_only=True) as wh:
        warehouse = dict(wh.execute("select project_id, status from raw.projects").fetchall())
    assert warehouse == dict(src.execute("select project_id, status from projects").fetchall())


def _sheet(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    return list(ws.iter_rows(values_only=True))


def test_tracker_layouts_map_to_the_same_columns():
    front = _sheet(
        [
            ["No.", "Project Code", "Project Name", "PIC", "Status", "Start", "End", "Extensions", "Latest update"],
            [1, "IBR-25-004", "Service network expansion in Spain", "Ana Ruiz", "Ongoing", "06/06/2025", "18/12/2026", 2, "pilot started"],
            [None] * 9,
            [2, "TRK2024-007", "Bodyshop partner network Portugal", "J. Costa", "", "TBD", "TBD", None, None],
        ]
    )
    middle = _sheet(
        [
            ["Parts Supply - project tracker"],
            ["#", "Ref", "Project", "Owner", "Stage", "Start date", "Due date", "Ext.", "Comments"],
            [
                1,
                "PAL-25-002",
                "Back-order reduction",
                "SMITH John",
                "Close report pending",
                dt.datetime(2025, 3, 1),
                "30.06.2025",
                None,
                "done",
            ],
        ]
    )
    layout_f, rows_f = parse_sheet(front)
    layout_m, rows_m = parse_sheet(middle)
    assert (layout_f, layout_m) == ("front", "middle")
    assert [r["project_ref"] for r in rows_f] == ["IBR-25-004", "TRK2024-007"]  # blank row skipped
    assert rows_f[1]["source_row"] == 4
    assert rows_f[1]["status"] is None
    assert rows_m[0] | {"source_row": 0} == {
        "source_row": 0,
        "row_no": "1",
        "project_ref": "PAL-25-002",
        "project_name": "Back-order reduction",
        "owner": "SMITH John",
        "status": "Close report pending",
        "start_raw": "2025-03-01",
        "end_raw": "30.06.2025",
        "extensions": None,
        "latest_update": "done",
    }
    assert set(rows_f[0]) == set(rows_m[0])


def test_sheet_without_header_is_skipped():
    assert parse_sheet(_sheet([["just a note"], ["nothing else"]])) == ("unknown", [])


def test_rebuilt_source_triggers_full_reload(tmp_path):
    """After `simulator init` rebuilds the source, the next load must not mix old and new rows."""
    from simulator.api import FULL_REFRESH_MARKER, init_world

    url = f"sqlite:///{tmp_path / 'source.db'}"
    init_world(url, tmp_path, seed=1, start=dt.date(2025, 1, 1), end=dt.date(2025, 4, 30))
    assert (tmp_path / FULL_REFRESH_MARKER).exists()
    run(url, tmp_path / "warehouse.duckdb", tmp_path / "excel")
    assert not (tmp_path / FULL_REFRESH_MARKER).exists()
    # rebuild with a different seed and a shorter history: ids get reused, counts shrink
    init_world(url, tmp_path, seed=2, start=dt.date(2025, 1, 1), end=dt.date(2025, 3, 15))
    run(url, tmp_path / "warehouse.duckdb", tmp_path / "excel")
    _counts_match(tmp_path)
