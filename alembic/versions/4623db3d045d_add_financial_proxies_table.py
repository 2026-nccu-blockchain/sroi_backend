
"""add financial proxies table

Revision ID: 4623db3d045d
Revises: e8f1a2b3c4d5
Create Date: 2026-10-22 15:28:50.621016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4623db3d045d"
down_revision: Union[str, None] = "e8f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_proxies",
        sa.Column(
            "proxy_id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "value",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column(
            "note",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("accounts.user_id"),
            nullable=False,
        ),
        sa.Column(
            "is_delete",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_financial_proxies_created_by",
        "financial_proxies",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_proxies_created_by",
        table_name="financial_proxies",
    )

    op.drop_table("financial_proxies")
