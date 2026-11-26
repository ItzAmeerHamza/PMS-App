"""Bring the local database to the latest Alembic revision on startup.

This is the only startup path that changes schema. It never deletes the file.
If the database already holds tables and a migration is pending, a backup is
taken first (label ``pre-migration``).
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from .backup import create_backup
from .database import get_engine
from .paths import BACKEND_ROOT

log = logging.getLogger("pharmacare.migrate")


def alembic_config(connection=None) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine | None = None) -> str | None:
    engine = engine or get_engine()
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def run_migrations(engine: Engine | None = None, backup: bool = True) -> dict:
    engine = engine or get_engine()
    db_path = Path(engine.url.database)
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        has_tables = bool(inspect(conn).get_table_names())
    head = head_revision()

    backup_path = None
    if backup and has_tables and current != head:
        # Next to the database being migrated, not the configured data dir: they differ
        # when a copy or another file is migrated.
        backup_path = create_backup(
            source=db_path, dest_dir=db_path.parent / "backups", label=f"pre-migration-{current or 'legacy'}"
        )
        log.info("Backed up the database before migrating: %s", backup_path.name)

    with engine.connect() as conn:
        command.upgrade(alembic_config(conn), "head")
        violations = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()

    counts: dict[str, int] = {}
    for table, *_ in violations:
        counts[table] = counts.get(table, 0) + 1
    if counts:
        # Table names and counts only: never row contents.
        log.warning("Foreign key violations in existing rows: %s", counts)
    return {"from": current, "to": head, "backup": backup_path, "foreign_key_violations": counts}
