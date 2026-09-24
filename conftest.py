"""Root pytest configuration.

Puts `server/` on sys.path so tests can `import app...` and `import utils...`
regardless of the directory pytest was invoked from. This replaces the
per-file `sys.path.insert` blocks the test modules used to carry.
"""

import sys
from pathlib import Path

# The supported floor is 3.9 (config.py evaluates `-> list[str]` at import, a
# PEP 585 generic). CI pins 3.11, so syntax newer than the floor — a PEP 604
# `X | None` annotation, say — passes there and then hard-fails at import for
# anyone whose venv was built from an older interpreter. Fail loudly here
# instead of collecting six cryptic TypeErrors.
MIN_PYTHON = (3, 9)
if sys.version_info < MIN_PYTHON:
    raise RuntimeError(
        f"NebulaML needs Python {'.'.join(map(str, MIN_PYTHON))}+, "
        f"got {sys.version.split()[0]}. Rebuild server/venv with a newer interpreter."
    )

SERVER_ROOT = Path(__file__).resolve().parent / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
