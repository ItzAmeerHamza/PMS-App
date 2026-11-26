"""Alembic environment for the local SQLite database.

Foreign keys are switched off while migrations run, because SQLite batch
migrations copy and recreate tables. They are switched back on afterwards, and
src.core.migrate runs PRAGMA foreign_key_check.
"""

import sys
from pathlib import Path

from alembic import context

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src import models  # noqa: E402,F401  (registers every live table on Base)
from src.core.database import Base, get_engine  # noqa: E402

target_metadata = Base.metadata


def _run(connection) -> None:
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.commit()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with get_engine().connect() as connection:
        _run(connection)


if context.is_offline_mode():
    raise SystemExit("Offline SQL generation is not supported for the local SQLite database.")
run_migrations_online()
