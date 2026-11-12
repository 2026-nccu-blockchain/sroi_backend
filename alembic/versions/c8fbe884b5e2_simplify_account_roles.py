"""simplify account roles

Revision ID: c8fbe884b5e2
Revises: 7065abb82f58
Create Date: 2026-10-28 18:43:05.088703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8fbe884b5e2'
down_revision: Union[str, None] = '7065abb82f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


role_enum = postgresql.ENUM("ADMIN", "DB_EDITOR", "NORMAL", name="role")
old_role_enum = postgresql.ENUM(
    "ADMIN", "DB_EDITOR", "VERIFIED", "IN_PROGRESS", "UNVERIFIED", "LEADER", "MEMBER", name="role"
)
group_status_enum = postgresql.ENUM("VERIFIED", "IN_PROGRESS", "UNVERIFIED", name="groupstatus")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 群組審核狀態從共用的 role enum 拆出來
    group_status_enum.create(bind)
    op.execute("ALTER TABLE groups ALTER COLUMN status TYPE groupstatus USING status::text::groupstatus")

    # 2. 使用者角色只剩 ADMIN / DB_EDITOR / NORMAL，其餘一律改為 NORMAL
    op.execute("ALTER TYPE role RENAME TO role_old")
    role_enum.create(bind)
    op.execute("""
        ALTER TABLE accounts ALTER COLUMN role TYPE role
        USING (CASE WHEN role::text IN ('ADMIN', 'DB_EDITOR') THEN role::text ELSE 'NORMAL' END)::role
    """)
    op.execute("DROP TYPE role_old")

    # 3. 移除首次驗證流程，學號變更不再附學生證
    op.execute("DELETE FROM verified_in_progress WHERE is_ver = true")
    op.drop_column("verified_in_progress", "is_ver")
    op.drop_column("verified_in_progress", "id_card_link")
    op.drop_column("accounts", "id_card_link")


def downgrade() -> None:
    bind = op.get_bind()

    op.add_column("accounts", sa.Column("id_card_link", sa.String(length=255), nullable=True))
    op.add_column("verified_in_progress", sa.Column("id_card_link", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("verified_in_progress", sa.Column("is_ver", sa.Boolean(), nullable=False, server_default=sa.false()))

    # NORMAL 無法分辨原本是否驗證過，一律還原成 VERIFIED
    op.execute("ALTER TYPE role RENAME TO role_new")
    old_role_enum.create(bind)
    op.execute("""
        ALTER TABLE accounts ALTER COLUMN role TYPE role
        USING (CASE WHEN role::text = 'NORMAL' THEN 'VERIFIED' ELSE role::text END)::role
    """)
    op.execute("ALTER TABLE groups ALTER COLUMN status TYPE role USING status::text::role")
    op.execute("DROP TYPE role_new")
    group_status_enum.drop(bind)
