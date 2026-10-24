"""add project outcomes and actual input cost

Revision ID: f9a3b4c5d6e7
Revises: e8f1a2b3c4d5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a3b4c5d6e7"
down_revision: Union[str, None] = "e8f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "actual_input_cost",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "project_outcomes",
        sa.Column("outcome_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outcome_id"),
    )
    op.create_index(op.f("ix_project_outcomes_outcome_id"), "project_outcomes", ["outcome_id"], unique=False)
    op.create_index(op.f("ix_project_outcomes_project_id"), "project_outcomes", ["project_id"], unique=False)
    op.create_table(
        "project_interview_files",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(op.f("ix_project_interview_files_file_id"), "project_interview_files", ["file_id"], unique=False)
    op.create_index(op.f("ix_project_interview_files_project_id"), "project_interview_files", ["project_id"], unique=False)
    op.add_column("pages", sa.Column("project_outcome_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_pages_project_outcome_id",
        "pages",
        "project_outcomes",
        ["project_outcome_id"],
        ["outcome_id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_pages_project_outcome_id"), "pages", ["project_outcome_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pages_project_outcome_id"), table_name="pages")
    op.drop_constraint("fk_pages_project_outcome_id", "pages", type_="foreignkey")
    op.drop_column("pages", "project_outcome_id")
    op.drop_index(op.f("ix_project_interview_files_project_id"), table_name="project_interview_files")
    op.drop_index(op.f("ix_project_interview_files_file_id"), table_name="project_interview_files")
    op.drop_table("project_interview_files")
    op.drop_index(op.f("ix_project_outcomes_project_id"), table_name="project_outcomes")
    op.drop_index(op.f("ix_project_outcomes_outcome_id"), table_name="project_outcomes")
    op.drop_table("project_outcomes")
    op.drop_column("projects", "actual_input_cost")
