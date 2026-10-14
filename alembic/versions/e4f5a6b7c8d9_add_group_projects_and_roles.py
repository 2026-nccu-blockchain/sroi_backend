"""add group projects and group roles

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


group_role_enum = postgresql.ENUM("LEADER", "EDITOR", "VIEWER", name="grouprole")


def upgrade() -> None:
    # 群組角色從共用的 role enum 拆出來：LEADER 維持組長，原本的 MEMBER 改為編輯者
    group_role_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        """
        ALTER TABLE group_account
        ALTER COLUMN group_role TYPE grouprole
        USING (CASE WHEN group_role::text = 'LEADER' THEN 'LEADER' ELSE 'EDITOR' END)::grouprole
        """
    )

    # 專案擁有者：個人（owner_id）或群組（group_id）二擇一
    op.add_column("projects", sa.Column("group_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_projects_group_id", "projects", "groups", ["group_id"], ["group_id"])
    op.create_index(op.f("ix_projects_group_id"), "projects", ["group_id"], unique=False)

    op.add_column("projects", sa.Column("created_by", sa.String(length=36), nullable=True))
    op.execute("UPDATE projects SET created_by = owner_id")
    op.alter_column("projects", "created_by", nullable=False)
    op.create_foreign_key("fk_projects_created_by", "projects", "accounts", ["created_by"], ["user_id"])

    op.alter_column("projects", "owner_id", nullable=True)
    op.create_check_constraint(
        "ck_project_single_owner",
        "projects",
        "(owner_id IS NOT NULL AND group_id IS NULL) OR (owner_id IS NULL AND group_id IS NOT NULL)",
    )


def downgrade() -> None:
    # 舊結構沒辦法表示群組專案，有資料就中止，避免直接刪掉
    bind = op.get_bind()
    group_projects = bind.execute(sa.text("SELECT COUNT(*) FROM projects WHERE group_id IS NOT NULL")).scalar()
    if group_projects:
        raise RuntimeError(f"Cannot downgrade: {group_projects} group project(s) exist")

    op.drop_constraint("ck_project_single_owner", "projects", type_="check")
    op.alter_column("projects", "owner_id", nullable=False)
    op.drop_constraint("fk_projects_created_by", "projects", type_="foreignkey")
    op.drop_column("projects", "created_by")
    op.drop_index(op.f("ix_projects_group_id"), table_name="projects")
    op.drop_constraint("fk_projects_group_id", "projects", type_="foreignkey")
    op.drop_column("projects", "group_id")

    op.execute(
        """
        ALTER TABLE group_account
        ALTER COLUMN group_role TYPE role
        USING (CASE WHEN group_role::text = 'LEADER' THEN 'LEADER' ELSE 'MEMBER' END)::role
        """
    )
    group_role_enum.drop(op.get_bind(), checkfirst=True)
