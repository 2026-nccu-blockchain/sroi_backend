"""add financial proxy currency

Revision ID: e0f1a2b3c4d5
Revises: 4d7c62529d90
"""

from alembic import op
import sqlalchemy as sa


revision = "e0f1a2b3c4d5"
down_revision = "4d7c62529d90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "financial_proxies",
        sa.Column("currency", sa.String(3), nullable=False, server_default="TWD"),
    )
    op.alter_column(
        "project_outcome_valuations",
        "financial_proxy_value",
        existing_type=sa.Numeric(14, 2),
        type_=sa.Numeric(18, 4),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "project_outcome_valuations",
        "financial_proxy_value",
        existing_type=sa.Numeric(18, 4),
        type_=sa.Numeric(14, 2),
        existing_nullable=False,
    )
    op.drop_column("financial_proxies", "currency")
