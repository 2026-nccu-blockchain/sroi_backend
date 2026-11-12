"""add form outcome sync cursor

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-11-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("outcome_sync_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_outcomes",
        sa.Column("sync_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                outcome_id,
                ROW_NUMBER() OVER (
                    PARTITION BY project_id
                    ORDER BY create_time, outcome_id
                ) AS sync_index
            FROM project_outcomes
        )
        UPDATE project_outcomes AS outcome
        SET sync_index = ranked.sync_index
        FROM ranked
        WHERE ranked.outcome_id = outcome.outcome_id
        """
    )
    op.execute(
        """
        UPDATE projects AS project
        SET outcome_sync_sequence = COALESCE(
            (
                SELECT MAX(outcome.sync_index)
                FROM project_outcomes AS outcome
                WHERE outcome.project_id = project.project_id
            ),
            0
        )
        """
    )
    op.create_index(
        "ix_project_outcomes_project_sync_index",
        "project_outcomes",
        ["project_id", "sync_index"],
        unique=False,
    )
    op.add_column(
        "forms",
        sa.Column("outcome_sync_index", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("forms", "outcome_sync_index")
    op.drop_index("ix_project_outcomes_project_sync_index", table_name="project_outcomes")
    op.drop_column("project_outcomes", "sync_index")
    op.drop_column("projects", "outcome_sync_sequence")
