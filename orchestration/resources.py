"""Where the pipeline reads and writes. One resource, so a test or a deployment can point
the whole pipeline at another folder or database by changing a single setting."""

import os
from pathlib import Path

from dagster import ConfigurableResource

REPO_ROOT = Path(__file__).resolve().parents[1]


def _default_data_dir() -> str:
    return str(Path(os.getenv("DATA_DIR", REPO_ROOT / "data")).resolve())


class PmoSettings(ConfigurableResource):
    """Paths and seed for the simulated source, the tracker files and the warehouse."""

    data_dir: str = _default_data_dir()
    source_db_url: str | None = os.getenv("SOURCE_DB_URL")  # default: SQLite file in data_dir
    seed: int = int(os.getenv("SIM_SEED", "42"))

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def source_url(self) -> str:
        return self.source_db_url or f"sqlite:///{self.data_path / 'source.db'}"

    @property
    def warehouse_path(self) -> Path:
        return self.data_path / "warehouse.duckdb"

    @property
    def tracker_dir(self) -> Path:
        return self.data_path / "excel"
