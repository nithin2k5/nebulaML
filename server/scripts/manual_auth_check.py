"""Manual smoke check for the auth endpoints against a running server.

Not a pytest test — it needs a live API and it mutates real accounts, so it
lives in scripts/ and is run by hand:

    python scripts/manual_auth_check.py --base-url http://localhost:8000

The addresses it exercises are supplied on the command line; the previous
version had real personal email addresses committed into the file.
"""

import argparse
import sys
import uuid

import requests


def _post(base_url: str, path: str, payload: dict) -> None:
    url = f"{base_url.rstrip('/')}/api/auth{path}"
    try:
        resp = requests.post(url, json=payload, timeout=10)
    except requests.RequestException as exc:
        print(f"  ✗ {path}: request failed: {exc}")
        return
    print(f"  {path}: HTTP {resp.status_code}")
    try:
        print(f"    {resp.json()}")
    except ValueError:
        print(f"    {resp.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help="Existing account to try logging in as. Repeatable.",
    )
    args = parser.parse_args()

    print(f"Target: {args.base_url}")

    for email in args.email:
        print(f"\n--- Login for {email} ---")
        _post(args.base_url, "/login", {"email": email})

    # Register and immediately log in a throwaway account.
    throwaway = f"selfcheck-{uuid.uuid4().hex[:10]}@example.com"
    print(f"\n--- Registration round-trip ({throwaway}) ---")
    _post(
        args.base_url,
        "/register",
        {"username": throwaway.split("@")[0], "email": throwaway, "role": "user"},
    )
    _post(args.base_url, "/login", {"email": throwaway})
    return 0


if __name__ == "__main__":
    sys.exit(main())
