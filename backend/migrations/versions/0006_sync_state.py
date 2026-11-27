"""Sync worker state, and an origin flag on the outbox.

- sync_outbox.origin: ``live`` (a counter change) or ``bootstrap`` (the one-time
  upload of rows that existed before sync). Existing rows are ``live``.
- sync_state: one row per pharmacy for activation, bootstrap progress, and the
  last sync outcome. The device secret is not a column here.

Revision ID: 0006_sync_state
Revises: 0005_sync_outbox
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_sync_state"
down_revision = "0005_sync_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sync_outbox") as batch:
        batch.add_column(sa.Column("origin", sa.String(length=20), nullable=False, server_default="live"))
        batch.create_check_constraint("ck_sync_outbox_origin", "origin IN ('live', 'bootstrap')")
    op.create_index("ix_sync_outbox_origin", "sync_outbox", ["origin", "status", "sequence"])

    op.create_table(
        "sync_state",
        sa.Column("pharmacy_id", sa.Integer(), nullable=False),
        sa.Column("bootstrap_status", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("bootstrap_stage", sa.String(length=20), nullable=False, server_default="products"),
        sa.Column("bootstrap_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_acknowledged_sequence", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backoff_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloud_api_url", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "bootstrap_status IN ('not_started', 'running', 'complete')", name="ck_sync_state_bootstrap_status"
        ),
        sa.CheckConstraint(
            "bootstrap_stage IN ('products', 'movements', 'patients', 'prescriptions', 'done')",
            name="ck_sync_state_bootstrap_stage",
        ),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.PrimaryKeyConstraint("pharmacy_id"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_index("ix_sync_outbox_origin", table_name="sync_outbox")
    with op.batch_alter_table("sync_outbox") as batch:
        batch.drop_constraint("ck_sync_outbox_origin", type_="check")
        batch.drop_column("origin")
