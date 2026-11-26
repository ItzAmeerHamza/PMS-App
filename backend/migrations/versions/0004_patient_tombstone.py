"""Patient tombstones: patients.deleted_at.

Removing a patient sets deleted_at instead of deleting the row, so prescriptions,
bills, and a later sync delete event can still refer to it.

Revision ID: 0004_patient_tombstone
Revises: 0003_stock_movements
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_patient_tombstone"
down_revision = "0003_stock_movements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_patients_deleted_at", "patients", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_patients_deleted_at", table_name="patients")
    with op.batch_alter_table("patients") as batch:
        batch.drop_column("deleted_at")
