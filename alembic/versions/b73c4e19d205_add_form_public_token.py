"""add form public token

Revision ID: b73c4e19d205
Revises: a21f0c9e8b42
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b73c4e19d205"
down_revision: Union[str, None] = "a21f0c9e8b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("forms", sa.Column("public_token", sa.String(length=32)))
    op.execute(
        """
        UPDATE forms
        SET public_token = substr(md5(random()::text || clock_timestamp()::text || form_id), 1, 24)
        WHERE status = 'PUBLISHED' AND public_token IS NULL
        """
    )
    op.create_index("ix_forms_public_token", "forms", ["public_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_forms_public_token", table_name="forms")
    op.drop_column("forms", "public_token")
