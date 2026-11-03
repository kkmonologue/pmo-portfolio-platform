"""Live JSON API over the warehouse, plus the portal's static files.

    uv run python -m portal serve      # http://localhost:8000, API docs at /docs

Every request opens its own read-only DuckDB connection and closes it straight after, so the
portal never holds the file open while a Dagster run needs to write to it.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .data import PAGES, Portal, WarehouseNotReady

STATIC = Path(__file__).parent / "static"


def create_app(warehouse: str | Path) -> FastAPI:
    app = FastAPI(
        title="PMO portal API",
        description="Read-only views over the dbt marts of the fictional Elvanor after-sales PMO.",
        version="1.0",
    )

    def load(fn):
        try:
            portal = Portal(warehouse)
        except (FileNotFoundError, WarehouseNotReady) as err:
            raise HTTPException(503, str(err)) from err
        try:
            return fn(portal)
        finally:
            portal.close()

    @app.get("/api/projects/{project_id}.json", summary="One project: milestones, history, requests, updates with extracted signals, risks")
    def project(project_id: int):
        data = load(lambda p: p.project(project_id))
        if data is None:
            raise HTTPException(404, f"No project {project_id}")
        return data

    @app.get("/api/{page}.json", summary="One portal page: " + ", ".join(PAGES))
    def page(page: str):
        if page not in PAGES:
            raise HTTPException(404, f"Unknown page {page!r}; one of {', '.join(PAGES)}")
        return load(lambda p: getattr(p, page)())

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
