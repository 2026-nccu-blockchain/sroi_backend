"""remove withdrawn cost detail fields

Revision ID: 9d5e6f7a8b01
Revises: 8c4d5e6f7a90
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "9d5e6f7a8b01"
down_revision: Union[str, None] = "8c4d5e6f7a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One deployed database already had project_costs before it entered the
    # migration history. Remove only the two fields from the withdrawn feature;
    # never drop that existing table or its data.
    if context.is_offline_mode():
        op.drop_column("project_costs", "funding_source")
        op.drop_column("project_costs", "quantity")
        return

    inspector = sa.inspect(op.get_bind())
    if "project_costs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project_costs")}
    if "funding_source" in columns:
        op.drop_column("project_costs", "funding_source")
    if "quantity" in columns:
        op.drop_column("project_costs", "quantity")


def downgrade() -> None:
    # The detail fields were withdrawn and are intentionally not recreated.
    pass
