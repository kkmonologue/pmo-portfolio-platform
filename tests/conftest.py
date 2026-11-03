import os

import pytest

os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")


@pytest.fixture(scope="session")
def runs(tmp_path_factory):
    """Two runs of the whole Dagster graph in a temporary folder: a backfill, then one more week.
    Shared by the orchestration and portal tests, so the pipeline is built only once."""
    from dagster import materialize

    from orchestration.assets import pmo_app_simulation, raw_ingestion, raw_matches_source, status_update_signals, warehouse_dbt
    from orchestration.definitions import defs
    from orchestration.resources import PmoSettings

    assets = [pmo_app_simulation, raw_ingestion, raw_matches_source, status_update_signals, warehouse_dbt]
    data = tmp_path_factory.mktemp("dagster_data")
    resources = {"settings": PmoSettings(data_dir=str(data)), "dbt": defs.resources["dbt"]}
    first = materialize(assets, resources=resources, raise_on_error=False)
    second = materialize(
        assets, resources=resources, raise_on_error=False, run_config={"ops": {"pmo_app_simulation": {"config": {"days": 7}}}}
    )
    return data, first, second
