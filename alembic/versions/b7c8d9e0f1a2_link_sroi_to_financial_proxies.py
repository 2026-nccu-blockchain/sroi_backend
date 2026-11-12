"""link stakeholder SROI to financial proxies

Revision ID: b7c8d9e0f1a2
Revises: 5a202633ce5d
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "5a202633ce5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_stakeholders",
        sa.Column(
            "sroi_discount_rate",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default="0.035",
        ),
    )
    op.execute(
        """
        UPDATE project_stakeholders AS stakeholder
        SET sroi_discount_rate = project.sroi_discount_rate
        FROM projects AS project
        WHERE project.project_id = stakeholder.project_id
        """
    )
    op.add_column(
        "project_outcome_valuations",
        sa.Column("financial_proxy_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_project_outcome_valuations_financial_proxy_id"),
        "project_outcome_valuations",
        ["financial_proxy_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_project_outcome_valuations_financial_proxy_id",
        "project_outcome_valuations",
        "financial_proxies",
        ["financial_proxy_id"],
        ["proxy_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_outcome_valuations_financial_proxy_id",
        "project_outcome_valuations",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_project_outcome_valuations_financial_proxy_id"),
        table_name="project_outcome_valuations",
    )
    op.drop_column("project_outcome_valuations", "financial_proxy_id")
    op.drop_column("project_stakeholders", "sroi_discount_rate")
