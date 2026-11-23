"""Make the ai-support-bot package importable for the reference tests.

Works both when ``reference_tests/`` is copied into the fixture root (as
verify_oracle.sh does) and when run in place from the answer-key directory.
Set SUPPORT_BOT_ROOT to point at a different checkout of the fixture.
"""

import os
import sys
from pathlib import Path


def _fixture_root() -> Path:
    env = os.environ.get("SUPPORT_BOT_ROOT")
    here = Path(__file__).resolve().parent
    candidates = [Path(env)] if env else []
    candidates += [here.parent, here.parents[3] / "examples" / "ai-support-bot"]
    for candidate in candidates:
        if (candidate / "support_bot" / "__init__.py").is_file():
            return candidate.resolve()
    raise RuntimeError("cannot locate the ai-support-bot fixture; set SUPPORT_BOT_ROOT")


_ROOT = str(_fixture_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
