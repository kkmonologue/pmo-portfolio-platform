"""Command line entry point.

python -m portal serve [--port 8000]     # live portal + API on the warehouse
python -m portal export [--out site]     # static copy for GitHub Pages or any web server
"""

import argparse
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
WAREHOUSE = Path(os.getenv("WAREHOUSE_PATH", DATA_DIR / "warehouse.duckdb"))


def main() -> None:
    ap = argparse.ArgumentParser(prog="portal", description="PMO portal over the warehouse marts")
    ap.add_argument("--warehouse", default=str(WAREHOUSE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the portal and its API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    e = sub.add_parser("export", help="write a static copy of the portal")
    e.add_argument("--out", default="site")
    args = ap.parse_args()

    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        print(f"Portal on http://{args.host}:{args.port}  (API docs: /docs)")
        uvicorn.run(create_app(args.warehouse), host=args.host, port=args.port, log_level="warning")
    else:
        from .export import export_site

        r = export_site(args.warehouse, args.out)
        print(f"Exported {r['pages']} pages and {r['projects']} project files to {args.out}/ ({r['bytes'] / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
