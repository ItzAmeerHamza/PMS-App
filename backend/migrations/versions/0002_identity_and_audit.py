"""Stable identity (public_id), entity versions, and the audit log.

- public_id: UUID text, unique, not null, on pharmacies, medicines, stock_batches,
  patients, prescriptions, prescription_items. Existing rows get a UUID here, once.
  The migration only fills rows whose public_id is NULL, so re-running it never
  changes an assigned id.
- version: integer, starts at 1, on medicines, patients, prescriptions.
- audit_logs: ids and action names only, no clinical text.

Revision ID: 0002_identity_and_audit
Revises: 0001_baseline
Create Date: 2026-11-26
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_identity_and_audit"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

IDENTITY_TABLES = [
    "pharmacies",
    "medicines",
    "stock_batches",
    "patients",
    "prescriptions",
    "prescription_items",
]
VERSIONED_TABLES = ["medicines", "patients", "prescriptions"]


def _columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def _fill_public_ids(table: str) -> None:
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text(f"SELECT id FROM {table} WHERE public_id IS NULL"))]
    for row_id in ids:
        bind.execute(
            sa.text(f"UPDATE {table} SET public_id = :public_id WHERE id = :id AND public_id IS NULL"),
            {"public_id": str(uuid.uuid4()), "id": row_id},
        )


def upgrade() -> None:
    for table in IDENTITY_TABLES:
        if "public_id" not in _columns(table):
            op.add_column(table, sa.Column("public_id", sa.String(36), nullable=True))
        _fill_public_ids(table)
        with op.batch_alter_table(table) as batch:
            batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        op.create_index(f"ix_{table}_public_id", table, ["public_id"], unique=True)

    for table in VERSIONED_TABLES:
        if "version" not in _columns(table):
            op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=True),
        sa.Column("entity_public_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_public_id", "audit_logs", ["public_id"], unique=True)
    op.create_index("ix_audit_logs_pharmacy_id", "audit_logs", ["pharmacy_id"])
    op.create_index("ix_audit_logs_staff_id", "audit_logs", ["staff_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    for table in VERSIONED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("version")
    for table in IDENTITY_TABLES:
        op.drop_index(f"ix_{table}_public_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("public_id")
