"""add projects and stakeholders

Revision ID: c4d8e1f2a903
Revises: ab026b738580
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8e1f2a903"
down_revision: Union[str, None] = "ab026b738580"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("linked_form_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("is_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["linked_form_id"], ["forms.form_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["accounts.user_id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index(op.f("ix_projects_project_id"), "projects", ["project_id"], unique=False)
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_index(op.f("ix_projects_linked_form_id"), "projects", ["linked_form_id"], unique=False)

    op.create_table(
        "project_stakeholders",
        sa.Column("stakeholder_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stakeholder_id"),
    )
    op.create_index(op.f("ix_project_stakeholders_stakeholder_id"), "project_stakeholders", ["stakeholder_id"], unique=False)
    op.create_index(op.f("ix_project_stakeholders_project_id"), "project_stakeholders", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_stakeholders_project_id"), table_name="project_stakeholders")
    op.drop_index(op.f("ix_project_stakeholders_stakeholder_id"), table_name="project_stakeholders")
    op.drop_table("project_stakeholders")
    op.drop_index(op.f("ix_projects_linked_form_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_project_id"), table_name="projects")
    op.drop_table("projects")
