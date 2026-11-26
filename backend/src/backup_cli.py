"""Backup and restore the local PharmaCare database from a terminal.

    cd backend
    .venv/bin/python -m src.backup_cli create            # safe while the app runs
    .venv/bin/python -m src.backup_cli list
    .venv/bin/python -m src.backup_cli restore <file>    # stop the app first

The data directory follows src/core/paths.py (PHARMACARE_DATA_DIR overrides it).
"""

import argparse
import sys
from pathlib import Path

from .core.backup import BackupError, create_backup, list_backups, restore_backup
from .core.paths import backup_dir, database_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.backup_cli", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="Write a backup of the live database")
    sub.add_parser("list", help="List backups, newest first")
    restore = sub.add_parser("restore", help="Replace the live database with a backup (app must be stopped)")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--yes", action="store_true", help="Confirm the PharmaCare app is not running")
    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            print(create_backup())
        elif args.command == "list":
            for path in list_backups():
                print(path)
            print(f"(backups folder: {backup_dir()})", file=sys.stderr)
        elif args.command == "restore":
            if not args.yes:
                print("Stop PharmaCare first, then run again with --yes.", file=sys.stderr)
                return 2
            kept = restore_backup(args.backup)
            print(f"Restored {args.backup} to {database_path()}")
            if kept != database_path():
                print(f"The previous database was kept as {kept}")
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
