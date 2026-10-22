"""add form shuffle setting

Revision ID: 6f3a2c1d9b80
Revises: f1a2b3c4d5e6
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f3a2c1d9b80"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing forms used shuffled outcome questions, so keep that behaviour by default.
    op.add_column(
        "forms",
        sa.Column(
            "shuffle_outcome_questions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("forms", "shuffle_outcome_questions")
