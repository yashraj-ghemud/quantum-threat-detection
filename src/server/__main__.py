"""``python -m server`` — run QVeris with uvicorn."""

from __future__ import annotations

import argparse

import uvicorn

from server.settings import Settings


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m server", description="Run the QVeris server.")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    args = ap.parse_args()
    s = Settings.from_env()
    host, port = args.host or s.host, args.port or s.port
    if args.reload:
        uvicorn.run("server.app:create_app", factory=True, host=host, port=port, reload=True,
                    reload_dirs=["src"], log_level=s.log_level.lower())
    else:
        from server.app import create_app

        uvicorn.run(create_app(s), host=host, port=port, log_level=s.log_level.lower(), ws_ping_interval=20)


if __name__ == "__main__":
    main()
