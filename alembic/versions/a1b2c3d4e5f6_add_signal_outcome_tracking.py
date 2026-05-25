"""add_signal_outcome_tracking

Revision ID: a1b2c3d4e5f6
Revises: d45b0fec6c57
Create Date: 2026-05-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d45b0fec6c57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("outcome", sa.String(length=20), nullable=True))
    op.add_column("signals", sa.Column("actual_exit_price", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("actual_rr", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "outcome_at")
    op.drop_column("signals", "actual_rr")
    op.drop_column("signals", "actual_exit_price")
    op.drop_column("signals", "outcome")
