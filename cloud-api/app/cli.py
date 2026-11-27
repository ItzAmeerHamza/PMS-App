"""One-off commands.

    python -m app.cli create-owner --email owner@example.com
        Password from the OWNER_PASSWORD environment variable, or prompted.
"""

import argparse
import getpass
import os
import sys

from .models.db import SessionLocal, get_engine
from .services.accounts import AccountError, create_owner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    owner = sub.add_parser("create-owner", help="Create an owner account")
    owner.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    password = os.environ.get("OWNER_PASSWORD") or getpass.getpass("Owner password: ")
    get_engine()
    db = SessionLocal()
    try:
        created = create_owner(db, args.email, password)
    except AccountError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"Owner {created.email} created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
