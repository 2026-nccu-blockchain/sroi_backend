"""link multiple forms to each project

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("forms", sa.Column("project_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_forms_project_id",
        "forms",
        "projects",
        ["project_id"],
        ["project_id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_forms_project_id"), "forms", ["project_id"], unique=False)

    # Preserve the form that was connected through the former one-form field.
    op.execute(
        sa.text(
            """
            UPDATE forms AS f
            SET project_id = p.project_id
            FROM projects AS p
            WHERE p.linked_form_id = f.form_id
              AND f.project_id IS NULL
            """
        )
    )


def downgrade() -> None:
    # Keep one usable link when rolling back to the former one-form model.
    op.execute(
        sa.text(
            """
            UPDATE projects AS p
            SET linked_form_id = selected.form_id
            FROM (
                SELECT DISTINCT ON (project_id) project_id, form_id
                FROM forms
                WHERE project_id IS NOT NULL AND is_delete = false
                ORDER BY project_id, create_time DESC NULLS LAST
            ) AS selected
            WHERE p.project_id = selected.project_id
              AND p.linked_form_id IS NULL
            """
        )
    )
    op.drop_index(op.f("ix_forms_project_id"), table_name="forms")
    op.drop_constraint("fk_forms_project_id", "forms", type_="foreignkey")
    op.drop_column("forms", "project_id")
