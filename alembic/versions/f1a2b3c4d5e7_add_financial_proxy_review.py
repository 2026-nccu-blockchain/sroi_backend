"""add financial proxy review

Revision ID: f1a2b3c4d5e7
Revises: e0f1a2b3c4d5
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e7"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "financial_proxies",
        sa.Column("review_status", sa.String(10), nullable=False, server_default="approved"),
    )
    op.alter_column("financial_proxies", "review_status", server_default="pending")
    op.add_column(
        "financial_proxies",
        sa.Column("reviewed_by", sa.String(36), nullable=True),
    )
    op.add_column(
        "financial_proxies",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_financial_proxy_reviewed_by", "financial_proxies", "accounts",
        ["reviewed_by"], ["user_id"],
    )
    op.create_check_constraint(
        "ck_financial_proxy_review_status", "financial_proxies",
        "review_status IN ('pending', 'approved', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_financial_proxy_review_status", "financial_proxies", type_="check")
    op.drop_constraint("fk_financial_proxy_reviewed_by", "financial_proxies", type_="foreignkey")
    op.drop_column("financial_proxies", "reviewed_at")
    op.drop_column("financial_proxies", "reviewed_by")
    op.drop_column("financial_proxies", "review_status")
