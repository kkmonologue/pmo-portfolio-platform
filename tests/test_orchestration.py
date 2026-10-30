import os

import duckdb
import pytest
from dagster import AssetKey, materialize

from orchestration.assets import pmo_app_simulation, raw_ingestion, raw_matches_source, status_update_signals, warehouse_dbt
from orchestration.definitions import defs
from orchestration.resources import PmoSettings

os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")
ASSETS = [pmo_app_simulation, raw_ingestion, raw_matches_source, status_update_signals, warehouse_dbt]


def test_definitions_load():
    graph = defs.resolve_asset_graph()
    keys = graph.get_all_asset_keys()
    assert AssetKey("pmo_app_simulation") in keys
    assert AssetKey(["app", "projects"]) in keys
    # dbt sources line up with the dlt assets, so lineage is one connected graph
    stg_projects = next(k for k in keys if k.path[-1] == "stg_app__projects")
    assert AssetKey(["app", "projects"]) in graph.get(stg_projects).parent_keys
    assert {j.name for j in defs.jobs} == {"weekly_pipeline", "refresh_warehouse"}
    # the extracted signals feed the dbt staging model, so the AI step sits inside the lineage
    stg_signals = next(k for k in keys if k.path[-1] == "stg_extract__status_update_signals")
    assert AssetKey(["extract", "status_update_signals"]) in graph.get(stg_signals).parent_keys


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    data = tmp_path_factory.mktemp("dagster_data")
    resources = {
        "settings": PmoSettings(data_dir=str(data)),
        "dbt": defs.resources["dbt"],
    }
    first = materialize(ASSETS, resources=resources, raise_on_error=False)
    second = materialize(
        ASSETS, resources=resources, raise_on_error=False, run_config={"ops": {"pmo_app_simulation": {"config": {"days": 7}}}}
    )
    return data, first, second


def test_first_run_backfills_and_builds_everything(runs):
    data, first, _ = runs
    assert first.success
    checks = first.get_asset_check_evaluations()
    assert checks and all(c.passed for c in checks), [c.check_name for c in checks if not c.passed]
    with duckdb.connect(str(data / "warehouse.duckdb"), read_only=True) as wh:
        assert wh.execute("select count(*) from marts.fct_projects").fetchone()[0] > 100
        assert wh.execute("select count(*) from marts.mart_project_risks").fetchone()[0] > 0
        # every update got signals (rules extractor, no API needed)
        assert (
            wh.execute("select count(*) from marts.fct_status_update_signals").fetchone()[0]
            == wh.execute("select count(*) from marts.fct_status_updates").fetchone()[0]
        )


def test_second_run_is_incremental(runs):
    _, first, second = runs
    assert second.success
    sim = second.asset_materializations_for_node("pmo_app_simulation")[0].metadata
    assert sim["days_simulated"].value == 7

    def loaded(result, key):
        mat = next(m for m in result.get_asset_materialization_events() if m.asset_key == key)
        return mat.materialization.metadata["rows_loaded_this_run"].value

    teams = AssetKey(["app", "teams"])
    updates = AssetKey(["app", "status_updates"])
    assert loaded(second, teams) == 0  # nothing changed there
    assert 0 < loaded(second, updates) < loaded(first, updates)
    assert all(c.passed for c in second.get_asset_check_evaluations())
