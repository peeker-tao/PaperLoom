"""Service entry point.

Usage:
    python -m paperloom_service --port 23124
    python -m paperloom_service --print-token
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from . import __version__
    from .config import api_key_status, load_runtime

    parser = argparse.ArgumentParser(prog="paperloom-service", description="PaperLoom local service")
    parser.add_argument("--port", type=int, default=None, help="loopback port (default 23124)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (loopback only)")
    parser.add_argument("--data-dir", default=None, help="data directory")
    parser.add_argument("--print-token", action="store_true", help="print instance token and exit")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ["PAPERLOOM_DATA_DIR"] = str(Path(args.data_dir).expanduser())

    cfg = load_runtime(args.port)
    cfg.host = args.host
    cfg.ensure_dirs()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(cfg.logs_dir / "service.log", encoding="utf-8"),
        ],
    )

    if args.version:
        print(__version__)
        return 0
    if args.print_token:
        print(cfg.token)
        return 0
    if args.check:
        from .db import Database

        db = Database(cfg.data_dir / "paperloom.sqlite")
        db.migrate()
        print(
            json.dumps(
                {
                    "ok": True,
                    "version": __version__,
                    "dataDir": str(cfg.data_dir),
                    "apiKey": api_key_status(cfg),
                    "db": str(db.path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if cfg.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing to bind a non-loopback address", file=sys.stderr)
        return 2

    import uvicorn

    from .app import create_app

    app = create_app(cfg)
    try:
        uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=cfg.log_level.lower())
    except OSError as exc:
        print(f"Failed to bind {cfg.host}:{cfg.port}: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
