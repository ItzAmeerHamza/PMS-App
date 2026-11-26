"""Stock movement ledger.

- Creates stock_movements (append-only; see models.StockMovement).
- Writes one `opening_balance` movement for every existing batch with a non-zero
  quantity, so that SUM(quantity_delta) per batch equals the batch quantity from
  the start. History before this migration is not reconstructed: sale_allocations
  remain the only batch-level record of earlier sales.
- Adds CHECK (quantity >= 0) to stock_batches.

Revision ID: 0003_stock_movements
Revises: 0002_identity_and_audit
Create Date: 2026-11-26
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0003_stock_movements"
down_revision = "0002_identity_and_audit"
branch_labels = None
depends_on = None

OPENING_REASON = "Balance when the stock ledger started"


def upgrade() -> None:
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("pharmacy_id", sa.Integer(), sa.ForeignKey("pharmacies.id"), nullable=False),
        sa.Column("medicine_id", sa.Integer(), sa.ForeignKey("medicines.id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("stock_batches.id"), nullable=False),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity_delta != 0", name="ck_stock_movements_delta_not_zero"),
        sa.CheckConstraint("quantity_after >= 0", name="ck_stock_movements_after_not_negative"),
        sa.CheckConstraint(
            "movement_type IN ('opening_balance', 'receipt', 'adjustment', 'dispense', 'sale', 'void')",
            name="ck_stock_movements_type",
        ),
    )
    for column, unique in (("id", False), ("public_id", True), ("pharmacy_id", False), ("medicine_id", False),
                           ("batch_id", False), ("created_at", False)):
        op.create_index(f"ix_stock_movements_{column}", "stock_movements", [column], unique=unique)

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT b.id, b.medicine_id, m.pharmacy_id, b.quantity FROM stock_batches b "
        "JOIN medicines m ON m.id = b.medicine_id WHERE b.quantity != 0 ORDER BY b.id"
    )).fetchall()
    # Same text format SQLAlchemy writes for DateTime on SQLite (UTC, no offset).
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    for batch_id, medicine_id, pharmacy_id, quantity in rows:
        bind.execute(
            sa.text(
                "INSERT INTO stock_movements (public_id, pharmacy_id, medicine_id, batch_id, movement_type, "
                "quantity_delta, quantity_after, reason, source_type, source_id, version, created_at) VALUES "
                "(:public_id, :pharmacy_id, :medicine_id, :batch_id, 'opening_balance', :qty, :qty, :reason, "
                "'migration', NULL, 1, :created_at)"
            ),
            {"public_id": str(uuid.uuid4()), "pharmacy_id": pharmacy_id, "medicine_id": medicine_id,
             "batch_id": batch_id, "qty": quantity, "reason": OPENING_REASON, "created_at": now},
        )

    with op.batch_alter_table("stock_batches") as batch:
        batch.create_check_constraint("ck_stock_batches_quantity_not_negative", "quantity >= 0")


def downgrade() -> None:
    with op.batch_alter_table("stock_batches") as batch:
        batch.drop_constraint("ck_stock_batches_quantity_not_negative", type_="check")
    op.drop_table("stock_movements")
