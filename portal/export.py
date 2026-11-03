"""Static export: the portal's files plus every API response as a JSON file, so the whole
portal runs from any static host (GitHub Pages) with no server and no database."""

import json
import shutil
from pathlib import Path

from .data import PAGES, Portal

STATIC = Path(__file__).parent / "static"


def export_site(warehouse: str | Path, out: str | Path) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out)
    (out / ".nojekyll").touch()  # serve files as they are on GitHub Pages
    api = out / "api"
    (api / "projects").mkdir(parents=True)
    portal = Portal(warehouse)
    try:
        for page in PAGES:
            (api / f"{page}.json").write_text(json.dumps(getattr(portal, page)(), separators=(",", ":")))
        ids = [r[0] for r in portal.con.execute("select project_id from marts.dim_project").fetchall()]
        for pid in ids:
            (api / "projects" / f"{pid}.json").write_text(json.dumps(portal.project(pid), separators=(",", ":")))
    finally:
        portal.close()
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    return {"pages": len(PAGES), "projects": len(ids), "bytes": size}
