"""add project costs

Revision ID: f1a2b3c4d5e6
Revises: 2254ddfe7a5f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "2254ddfe7a5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_costs",
        sa.Column("cost_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cost_id"),
    )
    op.create_index(op.f("ix_project_costs_cost_id"), "project_costs", ["cost_id"], unique=False)
    op.create_index(op.f("ix_project_costs_project_id"), "project_costs", ["project_id"], unique=False)

    # 舊專案已填的投入成本轉成一筆明細，避免總成本被歸零
    op.execute(
        """
        INSERT INTO project_costs (cost_id, project_id, name, price, description, position, is_delete)
        SELECT gen_random_uuid()::text, project_id, '投入成本', actual_input_cost, '', 0, false
        FROM projects
        WHERE actual_input_cost > 0
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_costs_project_id"), table_name="project_costs")
    op.drop_index(op.f("ix_project_costs_cost_id"), table_name="project_costs")
    op.drop_table("project_costs")
