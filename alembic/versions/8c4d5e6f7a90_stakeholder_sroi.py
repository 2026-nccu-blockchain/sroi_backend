"""stakeholder SROI

Revision ID: 8c4d5e6f7a90
Revises: 6f3a2c1d9b80
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "8c4d5e6f7a90"
down_revision: Union[str, None] = "6f3a2c1d9b80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    offline = context.is_offline_mode()
    valuation_columns = set() if offline else _column_names("project_outcome_valuations")
    if "stakeholder_id" not in valuation_columns:
        op.add_column(
            "project_outcome_valuations",
            sa.Column("stakeholder_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_project_outcome_valuations_stakeholder_id",
            "project_outcome_valuations",
            "project_stakeholders",
            ["stakeholder_id"],
            ["stakeholder_id"],
            ondelete="CASCADE",
        )
        op.create_index(
            op.f("ix_project_outcome_valuations_stakeholder_id"),
            "project_outcome_valuations",
            ["stakeholder_id"],
            unique=False,
        )

    # Existing outcome values are assigned to the first active stakeholder.
    op.execute(
        """
        UPDATE project_outcome_valuations v
        SET stakeholder_id = (
            SELECT s.stakeholder_id
            FROM project_stakeholders s
            WHERE s.project_id = v.project_id AND s.is_delete = false
            ORDER BY s.position, s.create_time, s.stakeholder_id
            LIMIT 1
        )
        WHERE v.stakeholder_id IS NULL
        """
    )

    unique_constraints = {"uq_project_outcome_valuation_outcome"} if offline else {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("project_outcome_valuations")
    }
    if "uq_project_outcome_valuation_outcome" in unique_constraints:
        op.drop_constraint(
            "uq_project_outcome_valuation_outcome",
            "project_outcome_valuations",
            type_="unique",
        )
    op.create_unique_constraint(
        "uq_project_outcome_valuation_stakeholder_outcome",
        "project_outcome_valuations",
        ["stakeholder_id", "outcome_id"],
    )


def downgrade() -> None:
    # Keep one valuation per outcome before restoring the old uniqueness rule.
    op.execute(
        """
        DELETE FROM project_outcome_valuations
        WHERE valuation_id IN (
            SELECT valuation_id FROM (
                SELECT valuation_id, row_number() OVER (
                    PARTITION BY outcome_id ORDER BY create_time, valuation_id
                ) AS row_number
                FROM project_outcome_valuations
            ) ranked
            WHERE row_number > 1
        )
        """
    )
    op.drop_constraint(
        "uq_project_outcome_valuation_stakeholder_outcome",
        "project_outcome_valuations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_project_outcome_valuation_outcome",
        "project_outcome_valuations",
        ["outcome_id"],
    )
    op.drop_index(
        op.f("ix_project_outcome_valuations_stakeholder_id"),
        table_name="project_outcome_valuations",
    )
    op.drop_constraint(
        "fk_project_outcome_valuations_stakeholder_id",
        "project_outcome_valuations",
        type_="foreignkey",
    )
    op.drop_column("project_outcome_valuations", "stakeholder_id")
