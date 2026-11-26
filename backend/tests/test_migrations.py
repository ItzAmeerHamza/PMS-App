import sqlite3

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from src import models  # noqa: F401
from src.core import database
from src.core.backup import list_backups
from src.core.database import Base
from src.core.migrate import current_revision, head_revision, run_migrations

from .legacy import build_oldest, build_pre_alembic, counts

IDENTITY_TABLES = ["pharmacies", "medicines", "stock_batches", "patients", "prescriptions", "prescription_items"]


def public_ids(path) -> dict[str, dict[int, str]]:
    conn = sqlite3.connect(path)
    try:
        return {table: dict(conn.execute(f"SELECT id, public_id FROM {table}").fetchall()) for table in IDENTITY_TABLES}
    finally:
        conn.close()


def schema_diff():
    with database.get_engine().connect() as conn:
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


@pytest.mark.parametrize("patched", [False, True], ids=["oldest-unpatched", "oldest-patched"])
def test_oldest_database_migrates_and_keeps_rows(db_path, patched):
    build_oldest(db_path, patched=patched)
    before = counts(db_path)

    result = run_migrations()

    assert result["from"] is None and result["to"] == head_revision()
    assert counts(db_path) == before
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT first_name, phone FROM patients WHERE id = 1").fetchone() == ("Alpha", "0300-0000001")
        assert conn.execute("SELECT quantity FROM stock_batches WHERE id = 1").fetchone() == (50,)
        # One-time data fixes from the baseline ran.
        assert conn.execute("SELECT salt FROM medicines WHERE id = 1").fetchone() == ("Testamol",)
        assert conn.execute("SELECT medicine_name FROM prescription_items WHERE id = 1").fetchone() == ("Testamol 500mg",)
        # Tables the oldest file never had now exist.
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"sales", "sale_items", "sale_allocations", "audit_logs", "alembic_version"} <= tables
        for table in ("medicines", "patients", "prescriptions"):
            assert {row[0] for row in conn.execute(f"SELECT DISTINCT version FROM {table}")} == {1}
    finally:
        conn.close()

    ids = public_ids(db_path)
    for table, mapping in ids.items():
        assert mapping, table
        assert all(mapping.values()), f"{table} has a NULL public_id"
        assert len(set(mapping.values())) == len(mapping), f"{table} public_id not unique"

    assert schema_diff() == []


def test_public_ids_are_assigned_once(db_path):
    build_oldest(db_path, patched=True)
    run_migrations()
    first = public_ids(db_path)

    again = run_migrations()
    assert again["from"] == again["to"] == head_revision()
    assert again["backup"] is None, "no backup when nothing is pending"
    assert public_ids(db_path) == first

    # The real startup path must not touch them either.
    from .conftest import start_client

    for _ in range(2):
        with start_client() as client:
            assert client.get("/health").status_code == 200
    assert public_ids(db_path) == first


def test_pre_alembic_database_with_billing_tables_migrates(db_path):
    build_pre_alembic(db_path)
    before = counts(db_path)
    result = run_migrations()
    assert result["to"] == head_revision()
    assert counts(db_path) == before
    assert schema_diff() == []


def test_backup_is_taken_before_migrating_existing_data(db_path, data_dir):
    build_oldest(db_path)
    result = run_migrations()
    assert result["backup"] is not None
    assert result["backup"].parent == data_dir / "backups"
    assert "pre-migration-legacy" in result["backup"].name
    assert counts(result["backup"]) == counts(db_path)
    assert list_backups() == [result["backup"]]


def test_empty_database_matches_models(db_path):
    result = run_migrations()
    assert result["backup"] is None, "nothing to back up on a fresh file"
    assert current_revision() == head_revision()
    assert schema_diff() == []


def test_downgrade_of_identity_migration_then_upgrade_keeps_rows(db_path):
    from alembic import command

    from src.core.migrate import alembic_config

    build_oldest(db_path, patched=True)
    run_migrations(backup=False)
    before = counts(db_path)
    with database.get_engine().connect() as conn:
        command.downgrade(alembic_config(conn), "0001_baseline")
    assert counts(db_path) == before
    run_migrations(backup=False)
    assert counts(db_path) == before
    assert schema_diff() == []


def test_ledger_starts_with_opening_balances(db_path):
    build_oldest(db_path, patched=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO stock_batches (id, medicine_id, batch_number, expiry_date, quantity) VALUES (3, 1, 'B-EMPTY', '2099-01-01', 0)")
        conn.commit()
    finally:
        conn.close()
    run_migrations(backup=False)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT batch_id, movement_type, quantity_delta, quantity_after, source_type FROM stock_movements ORDER BY batch_id"
        ).fetchall()
        unbalanced = conn.execute(
            "SELECT b.id FROM stock_batches b LEFT JOIN stock_movements m ON m.batch_id = b.id "
            "GROUP BY b.id HAVING b.quantity != COALESCE(SUM(m.quantity_delta), 0)"
        ).fetchall()
        public_ids = [row[0] for row in conn.execute("SELECT public_id FROM stock_movements")]
    finally:
        conn.close()
    assert rows == [(1, "opening_balance", 50, 50, "migration"), (2, "opening_balance", 30, 30, "migration")]
    assert unbalanced == [], "every batch quantity equals the sum of its movements"
    assert len(set(public_ids)) == 2 and all(len(p) == 36 for p in public_ids)


def test_void_of_a_bill_made_before_the_ledger_keeps_it_balanced(db_path):
    from .conftest import auth, set_up_manager, start_client

    build_pre_alembic(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # A bill sold before phase 03: 5 units taken from batch 1 (50 -> 45), no movement rows existed then.
        conn.execute("UPDATE stock_batches SET quantity = 45 WHERE id = 1")
        conn.execute("INSERT INTO sales (id, pharmacy_id, invoice_number, subtotal, discount_percent, discount_amount, tax_percent, "
                     "tax_amount, total, payment_method, amount_paid, change_due, status) "
                     "VALUES (1, 1, 'INV-000001', 50, 0, 0, 0, 0, 50, 'cash', 50, 0, 'paid')")
        conn.execute("INSERT INTO sale_items (id, sale_id, medicine_id, medicine_name, quantity, unit_price, line_total) "
                     "VALUES (1, 1, 1, 'Testamol 500mg', 5, 10, 50)")
        conn.execute("INSERT INTO sale_allocations (id, sale_item_id, batch_id, batch_number, expiry_date, quantity) "
                     "VALUES (1, 1, 1, 'B-1', '2099-01-01', 5)")
        conn.execute("DELETE FROM staff")  # the legacy manager row; set up a fresh one through the API
        conn.commit()
    finally:
        conn.close()
    with start_client() as client:
        headers = auth(set_up_manager(client))
        assert client.post("/api/v1/billing/sales/1/void", headers=headers, json={"reason": "pre-ledger return"}).status_code == 200
        history = client.get("/api/v1/inventory/medicines/1/movements", headers=headers).json()
    assert [(m["movement_type"], m["quantity_delta"], m["quantity_after"]) for m in history] == [
        ("opening_balance", 45, 45), ("void", 5, 50)]


def test_pre_migration_backup_sits_beside_the_migrated_file(data_dir, tmp_path):
    """Migrating a file outside the configured data dir must not write into that data dir."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    target = other / "copy.db"
    build_oldest(target)
    result = run_migrations(database.init_engine(target))
    assert result["backup"].parent == other / "backups"
    assert not (data_dir / "backups").exists() or list((data_dir / "backups").iterdir()) == []
