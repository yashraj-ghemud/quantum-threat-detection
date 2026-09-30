"""``python -m server.dump_openapi [out.json]`` — write the OpenAPI document without starting a server."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from server.settings import Settings


def main() -> None:
    from server.app import create_app

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings.from_env(data_dir=Path(tmp), background=False, skip_calibration=True))
        out.write_text(json.dumps(app.openapi(), indent=2))
        app.state.ctx.close()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
