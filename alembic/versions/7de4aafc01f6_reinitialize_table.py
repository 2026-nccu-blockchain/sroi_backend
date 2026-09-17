"""Update the existing schema to the consolidated account/group model.

Revision ID: 7de4aafc01f6
Revises: b73c4e19d205

Older databases are already at b73c4e19d205 and contain form data. Reusing
this revision ID as an incremental migration preserves that data. Databases
that previously applied 7de4aafc01f6 already have the target schema.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7de4aafc01f6"
down_revision: Union[str, None] = "b73c4e19d205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verified_in_progress",
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("is_ver", sa.Boolean(), nullable=False),
        sa.Column("campus_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("id_card_link", sa.String(length=255), nullable=False),
        sa.Column("is_delete", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("update_time", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index(op.f("ix_verified_in_progress_uuid"), "verified_in_progress", ["uuid"])

    # Rename instead of dropping account_id to retain existing memberships.
    op.alter_column(
        "group_account",
        "account_id",
        new_column_name="user_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
    )
    op.add_column("group_account", sa.Column("uuid", sa.String(length=36)))
    op.execute("UPDATE group_account SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    op.alter_column(
        "group_account",
        "uuid",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.add_column(
        "group_account",
        sa.Column("is_delete", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "group_account",
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column("group_account", sa.Column("update_time", sa.DateTime(timezone=True)))
    op.drop_constraint("group_account_pkey", "group_account", type_="primary")
    op.create_primary_key("group_account_pkey", "group_account", ["uuid"])
    op.create_index(op.f("ix_group_account_uuid"), "group_account", ["uuid"])


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrading the account/group schema could discard membership or "
        "verification data; restore a database backup instead."
    )
