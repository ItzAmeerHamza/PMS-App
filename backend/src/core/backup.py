"""Safe SQLite backups and offline restore.

Backups use SQLite's online backup API (``sqlite3.Connection.backup``), which copies
a consistent snapshot even while the app is running in WAL mode. Copying the
``.db`` file with the file system would miss pages that still sit in ``-wal``.

Restore is an offline operation: stop the app first. See docs/BACKUP_AND_RECOVERY.md.
"""

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .paths import backup_dir, database_path

KEEP_BACKUPS = 30


class BackupError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def check_integrity(path: Path) -> None:
    """Raise BackupError unless ``path`` is a readable, intact SQLite file."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Not a readable SQLite database: {path.name}") from exc
    if result != "ok":
        raise BackupError(f"Integrity check failed for {path.name}")


def create_backup(source: Path | None = None, dest_dir: Path | None = None, label: str = "manual") -> Path:
    source = Path(source) if source else database_path()
    if not source.exists():
        raise BackupError("There is no database to back up yet")
    dest_dir = Path(dest_dir) if dest_dir else backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)[:40] or "backup"
    target = dest_dir / f"pharmacy-{_timestamp()}-{safe_label}.db"
    partial = target.with_suffix(".db.partial")

    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(partial))
        try:
            src.backup(dst)
            # A backup file stands alone: no WAL sidecar files.
            dst.execute("PRAGMA journal_mode=DELETE")
        finally:
            dst.close()
    finally:
        src.close()
    check_integrity(partial)
    partial.replace(target)
    prune_backups(dest_dir)
    return target


def list_backups(dest_dir: Path | None = None) -> list[Path]:
    dest_dir = Path(dest_dir) if dest_dir else backup_dir()
    return sorted(dest_dir.glob("pharmacy-*.db"), reverse=True)


def prune_backups(dest_dir: Path, keep: int = KEEP_BACKUPS) -> None:
    for old in list_backups(dest_dir)[keep:]:
        old.unlink(missing_ok=True)


def restore_backup(backup: Path, target: Path | None = None) -> Path:
    """Replace the live database with ``backup``. Run only while the app is stopped.

    The current file is kept beside it as ``pharmacy.db.before-restore-<time>``.
    Returns the path of that kept file (or the target if nothing existed).
    """
    backup = Path(backup)
    target = Path(target) if target else database_path()
    if not backup.exists():
        raise BackupError(f"Backup not found: {backup}")
    check_integrity(backup)

    kept = target
    if target.exists():
        kept = target.with_name(f"{target.name}.before-restore-{_timestamp()}")
        # Fold any WAL content into the current file before setting it aside.
        conn = sqlite3.connect(str(target))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
        target.replace(kept)
    for suffix in ("-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)

    staging = target.with_name(f"{target.name}.restoring")
    shutil.copyfile(backup, staging)
    check_integrity(staging)
    staging.replace(target)
    return kept
