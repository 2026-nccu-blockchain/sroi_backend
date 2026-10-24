"""repair missing project interview files table

Revision ID: a0b1c2d3e4f5
Revises: f9a3b4c5d6e7

The interview-file table was added to an already-applied migration. Existing
databases therefore reported the latest revision without having the table.
This reconciliation migration is intentionally safe for both existing and
fresh databases.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "f9a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("project_interview_files"):
        return

    op.create_table(
        "project_interview_files",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(
        op.f("ix_project_interview_files_file_id"),
        "project_interview_files",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_interview_files_project_id"),
        "project_interview_files",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    # Revision f9a3b4c5d6e7 owns this table. Moving back to that revision should
    # preserve the schema it declares; its own downgrade removes the table.
    pass
