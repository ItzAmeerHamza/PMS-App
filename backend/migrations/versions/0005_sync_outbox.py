"""Transactional sync outbox, and medicine tombstones.

- sync_outbox: durable events written in the same transaction as each business
  change (docs/SYNC_PROTOCOL.md). Unique event_id and sequence; pending-read index
  (status, next_attempt_at, sequence).
- medicines.deleted_at: product.deleted is a tombstone; the row stays.

Rows that existed before this migration get no events here. Phase 07 Part B's
bootstrap uploads pre-existing data.

Revision ID: 0005_sync_outbox
Revises: 0004_patient_tombstone
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_sync_outbox"
down_revision = "0004_patient_tombstone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("shop_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
        sa.UniqueConstraint("event_id"),
        sa.CheckConstraint("status IN ('pending', 'synced', 'retryable_error', 'failed')", name="ck_sync_outbox_status"),
        sa.CheckConstraint("operation IN ('created', 'updated', 'deleted')", name="ck_sync_outbox_operation"),
    )
    op.create_index("ix_sync_outbox_pending", "sync_outbox", ["status", "next_attempt_at", "sequence"])
    op.create_index("ix_sync_outbox_entity_id", "sync_outbox", ["entity_id"])

    op.add_column("medicines", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_medicines_deleted_at", "medicines", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_medicines_deleted_at", table_name="medicines")
    with op.batch_alter_table("medicines") as batch:
        batch.drop_column("deleted_at")
    op.drop_table("sync_outbox")
