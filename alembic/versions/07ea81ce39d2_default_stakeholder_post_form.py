"""default unset post-test links to each stakeholder's dedicated form

Revision ID: 07ea81ce39d2
Revises: 6f2d9a4c83b1
"""

from alembic import op


revision = "07ea81ce39d2"
down_revision = "6f2d9a4c83b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE project_stakeholders AS stakeholder
        SET post_form_id = form.form_id
        FROM forms AS form
        JOIN projects AS project ON project.project_id = form.project_id
        WHERE form.stakeholder_id = stakeholder.stakeholder_id
          AND form.project_id = stakeholder.project_id
          AND NOT form.is_delete
          AND NOT stakeholder.is_delete
          AND NOT project.is_delete
          AND stakeholder.pre_form_id IS NULL
          AND stakeholder.post_form_id IS NULL
    """)


def downgrade() -> None:
    # 保留現有指定，因為升級後可能已有使用者確認或修改表單。
    pass
