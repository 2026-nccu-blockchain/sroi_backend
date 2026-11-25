"""add individual valuation exchange rate month

Revision ID: 39b54df7c261
Revises: f4db2bc5a9e1
"""

from alembic import op
import sqlalchemy as sa


revision = "39b54df7c261"
down_revision = "f4db2bc5a9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_outcome_valuations", sa.Column("exchange_rate_month", sa.String(7), nullable=True))
    op.execute("""
        UPDATE project_outcome_valuations AS valuation
        SET exchange_rate_month = stakeholder.sroi_exchange_rate_month
        FROM project_stakeholders AS stakeholder
        WHERE valuation.stakeholder_id = stakeholder.stakeholder_id
          AND stakeholder.sroi_exchange_rate_month IS NOT NULL
          AND valuation.financial_proxy_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("project_outcome_valuations", "exchange_rate_month")
