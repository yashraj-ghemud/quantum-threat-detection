import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import _agent_guard  # noqa: E402

_agent_guard.enforce()
