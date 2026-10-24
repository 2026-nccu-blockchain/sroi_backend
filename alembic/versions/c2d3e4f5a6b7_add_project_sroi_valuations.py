"""add project SROI valuations

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "sroi_discount_rate",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default="0.035",
        ),
    )
    op.create_table(
        "project_outcome_valuations",
        sa.Column("valuation_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("outcome_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("financial_proxy_value", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("deadweight_rate", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0"),
        sa.Column("attribution_rate", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0"),
        sa.Column("displacement_rate", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0"),
        sa.Column("duration_years", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dropoff_rate", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0"),
        sa.Column("is_included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["outcome_id"], ["project_outcomes.outcome_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("valuation_id"),
        sa.UniqueConstraint("outcome_id", name="uq_project_outcome_valuation_outcome"),
    )
    op.create_index(
        op.f("ix_project_outcome_valuations_valuation_id"),
        "project_outcome_valuations",
        ["valuation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_outcome_valuations_project_id"),
        "project_outcome_valuations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_outcome_valuations_outcome_id"),
        "project_outcome_valuations",
        ["outcome_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_outcome_valuations_outcome_id"), table_name="project_outcome_valuations")
    op.drop_index(op.f("ix_project_outcome_valuations_project_id"), table_name="project_outcome_valuations")
    op.drop_index(op.f("ix_project_outcome_valuations_valuation_id"), table_name="project_outcome_valuations")
    op.drop_table("project_outcome_valuations")
    op.drop_column("projects", "sroi_discount_rate")
