import os
import sqlite3

import pytest

from src.backup_cli import main as backup_cli
from src.core.backup import BackupError, check_integrity, create_backup, restore_backup
from src.core.database import get_engine
from src.core.migrate import run_migrations

from .conftest import start_client
from .legacy import build_oldest, counts


def marker(path) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT name FROM pharmacies WHERE id = 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_startup_keeps_an_existing_database(db_path):
    build_oldest(db_path, patched=True)
    inode = os.stat(db_path).st_ino
    before = counts(db_path)

    for _ in range(2):
        with start_client() as client:
            assert client.get("/health").status_code == 200

    assert os.stat(db_path).st_ino == inode, "the database file was replaced"
    assert counts(db_path) == before
    assert marker(db_path) == "Synthetic Pharmacy"


def test_fresh_start_has_no_default_account_or_sample_data(client, db_path):
    status = client.get("/api/v1/auth/setup").json()
    assert status == {"needs_setup": True, "has_pharmacy": False, "pharmacy_name": None}
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pharmacies").fetchone()[0] == 0
    finally:
        conn.close()
    bad = client.post("/api/v1/auth/login", json={"username": "manager", "password": "store123"})
    assert bad.status_code == 401


def test_backup_and_restore_round_trip(db_path, data_dir):
    build_oldest(db_path, patched=True)
    run_migrations(backup=False)

    # Write through the app engine (WAL mode) without checkpointing, then back up.
    with get_engine().begin() as conn:
        conn.exec_driver_sql("UPDATE pharmacies SET name = 'Before Backup' WHERE id = 1")
    assert os.path.exists(f"{db_path}-wal")
    backup = create_backup(label="test")
    assert backup.parent == data_dir / "backups"
    assert marker(backup) == "Before Backup", "backup must include pages still in the WAL"
    check_integrity(backup)

    with get_engine().begin() as conn:
        conn.exec_driver_sql("UPDATE pharmacies SET name = 'After Backup' WHERE id = 1")
        conn.exec_driver_sql("DELETE FROM prescription_items")
    get_engine().dispose()  # restore runs with the app stopped

    kept = restore_backup(backup)
    assert marker(db_path) == "Before Backup"
    assert counts(db_path)["prescription_items"] == 1
    assert marker(kept) == "After Backup", "the replaced database is kept beside the restored one"
    check_integrity(db_path)


def test_restore_refuses_a_corrupt_backup(db_path, tmp_path):
    build_oldest(db_path)
    bad = tmp_path / "pharmacy-bad.db"
    bad.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(BackupError):
        restore_backup(bad)
    assert marker(db_path) == "Synthetic Pharmacy"


def test_cli_restore_requires_confirmation(db_path, capsys):
    build_oldest(db_path)
    backup = create_backup()
    assert backup_cli(["restore", str(backup)]) == 2
    assert "Stop PharmaCare first" in capsys.readouterr().err
    assert backup_cli(["list"]) == 0
    assert str(backup) in capsys.readouterr().out
