"""add project closed_at and published_at

Revision ID: ca246ee74661
Revises: c8d9e0f1a2b3
Create Date: 2026-11-17 01:59:42.388379
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ca246ee74661"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "published_at")
    op.drop_column("projects", "closed_at")
