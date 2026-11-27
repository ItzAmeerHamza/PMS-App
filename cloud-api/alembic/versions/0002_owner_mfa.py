"""Owner TOTP challenges.

The pending secret lives only until the owner confirms a code. Session cookies
still use owner_sessions; this table is not a session.

Revision ID: 0002_owner_mfa
Revises: 0001_initial
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_owner_mfa"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_challenges",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=10), nullable=False),
        sa.Column("pending_secret", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("purpose IN ('enroll', 'totp')", name="ck_owner_challenges_purpose"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_owner_challenges_owner_id", "owner_challenges", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_owner_challenges_owner_id", table_name="owner_challenges")
    op.drop_table("owner_challenges")
