"""Root pytest configuration.

Puts `server/` on sys.path so tests can `import app...` and `import utils...`
regardless of the directory pytest was invoked from. This replaces the
per-file `sys.path.insert` blocks the test modules used to carry.
"""

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
