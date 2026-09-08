"""Manual MySQL connectivity check.

Not a pytest test — it needs a live MySQL server. Run it by hand when the API
fails to start and you want to isolate whether the database is reachable:

    python scripts/check_db_connection.py

Exits non-zero on failure so it can gate a deploy step.
"""

import sys

import mysql.connector

from app.core.config import settings


def main() -> int:
    print(f"Connecting to {settings.db_host}:{settings.db_port} as {settings.db_user}...")
    try:
        connection = mysql.connector.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
        )
    except Exception as exc:
        # The old version swallowed this and still exited 0, so a broken
        # database looked like a passing check.
        print(f"✗ Failed to connect: {exc}")
        return 1
    print("✓ Successfully connected to MySQL server")
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
