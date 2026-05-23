"""add_journal_strategy_outcome_emotional

Revision ID: a1b2c3d4e5f6
Revises: d45b0fec6c57
Create Date: 2026-05-19 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d45b0fec6c57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("journal_entries", sa.Column("strategy", sa.String(length=50), nullable=False, server_default=""))
    op.add_column("journal_entries", sa.Column("outcome", sa.String(length=20), nullable=False, server_default=""))
    op.add_column(
        "journal_entries", sa.Column("emotional_state", sa.String(length=30), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("journal_entries", "emotional_state")
    op.drop_column("journal_entries", "outcome")
    op.drop_column("journal_entries", "strategy")
