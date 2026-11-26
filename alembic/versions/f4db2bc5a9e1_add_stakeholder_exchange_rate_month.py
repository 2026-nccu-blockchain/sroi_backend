"""add stakeholder exchange rate month

Revision ID: f4db2bc5a9e1
Revises: f1a2b3c4d5e7
"""

from alembic import op
import sqlalchemy as sa


revision = "f4db2bc5a9e1"
down_revision = "f1a2b3c4d5e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_stakeholders",
        sa.Column("sroi_exchange_rate_month", sa.String(7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_stakeholders", "sroi_exchange_rate_month")
