"""add project review_requested_at

Revision ID: 6763c028447d
Revises: ca246ee74661
Create Date: 2026-11-17 18:50:06.627496
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6763c028447d"
down_revision: Union[str, None] = "ca246ee74661"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE projects SET review_requested_at = published_at "
        "WHERE published_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("projects", "review_requested_at")
