"""group roles group projects and group account cleanup

Revision ID: 2254ddfe7a5f
Revises: e4f5a6b7c8d9
Create Date: 2026-10-15 18:12:08.313827

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2254ddfe7a5f'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


group_role_enum = postgresql.ENUM("LEADER", "EDITOR", "VIEWER", name="grouprole")


def upgrade() -> None:
    # 1. 群組角色從共用的 role enum 拆出來：LEADER 維持組長，原本的 MEMBER 改為編輯者
    group_role_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        """
        ALTER TABLE group_account
        ALTER COLUMN group_role TYPE grouprole
        USING (CASE WHEN group_role::text = 'LEADER' THEN 'LEADER' ELSE 'EDITOR' END)::grouprole
        """
    )

    # 2. 專案擁有者：個人（owner_id）或群組（group_id）二擇一
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

    # 3. 陣列裡有、group_account 沒有的成員先補進來
    #    申請中 / 不同意的群組原本只記在 leader_list，補成 LEADER
    op.execute(
        """
        INSERT INTO group_account (uuid, group_id, user_id, group_role, is_delete, create_time)
        SELECT gen_random_uuid()::text, src.group_id, src.user_id, src.group_role::grouprole, false, now()
        FROM (
            SELECT DISTINCT g.group_id, l.user_id, 'LEADER' AS group_role
            FROM groups g CROSS JOIN LATERAL unnest(g.leader_list) AS l(user_id)
            UNION
            SELECT DISTINCT g.group_id, m.user_id, 'VIEWER' AS group_role
            FROM groups g CROSS JOIN LATERAL unnest(g.member_list) AS m(user_id)
            WHERE NOT (m.user_id = ANY(coalesce(g.leader_list, '{}')))
        ) AS src
        WHERE EXISTS (SELECT 1 FROM accounts a WHERE a.user_id = src.user_id)
          AND NOT EXISTS (
              SELECT 1 FROM group_account ga
              WHERE ga.group_id = src.group_id AND ga.user_id = src.user_id AND ga.is_delete = false
          )
        """
    )

    #    已經有 group_account 但角色不是組長、卻記在 leader_list 的人，以 leader_list 為準升為組長
    #    （舊版畫面的組長名單是讀 leader_list，避免轉換後群組變成沒有組長）
    op.execute(
        """
        UPDATE group_account ga SET group_role = 'LEADER'
        FROM groups g
        WHERE ga.group_id = g.group_id
          AND ga.is_delete = false
          AND ga.group_role <> 'LEADER'
          AND ga.user_id = ANY(coalesce(g.leader_list, '{}'))
        """
    )

    # 4. 清掉指向不存在群組 / 帳號的資料，否則加不了外鍵
    op.execute(
        """
        DELETE FROM group_account
        WHERE group_id NOT IN (SELECT group_id FROM groups)
           OR user_id NOT IN (SELECT user_id FROM accounts)
        """
    )

    # 5. 同一人同一群組有多筆有效資料時，保留權限最高、最早建立的那筆
    op.execute(
        """
        UPDATE group_account SET is_delete = true
        WHERE uuid IN (
            SELECT uuid FROM (
                SELECT uuid, row_number() OVER (
                    PARTITION BY group_id, user_id
                    ORDER BY CASE group_role::text WHEN 'LEADER' THEN 0 WHEN 'EDITOR' THEN 1 ELSE 2 END,
                             create_time NULLS LAST, uuid
                ) AS rn
                FROM group_account
                WHERE is_delete = false
            ) AS ranked
            WHERE rn > 1
        )
        """
    )

    # 6. 外鍵、索引、唯一約束
    op.create_foreign_key("fk_group_account_group_id", "group_account", "groups", ["group_id"], ["group_id"])
    op.create_foreign_key("fk_group_account_user_id", "group_account", "accounts", ["user_id"], ["user_id"])
    op.create_index(op.f("ix_group_account_group_id"), "group_account", ["group_id"], unique=False)
    op.create_index(op.f("ix_group_account_user_id"), "group_account", ["user_id"], unique=False)
    op.create_index(
        "uq_group_account_active",
        "group_account",
        ["group_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_delete = false"),
    )

    # 7. 成員一律以 group_account 為準，拿掉重複記錄的陣列
    op.drop_column("groups", "leader_list")
    op.drop_column("groups", "member_list")
    op.drop_column("accounts", "group_list")


def downgrade() -> None:
    # 舊結構沒辦法表示群組專案，有資料就中止，避免直接刪掉
    bind = op.get_bind()
    group_projects = bind.execute(sa.text("SELECT COUNT(*) FROM projects WHERE group_id IS NOT NULL")).scalar()
    if group_projects:
        raise RuntimeError(f"Cannot downgrade: {group_projects} group project(s) exist")

    # 7. 從 group_account 還原陣列
    op.add_column("accounts", sa.Column("group_list", postgresql.ARRAY(sa.String(length=255)), nullable=True))
    op.add_column("groups", sa.Column("member_list", postgresql.ARRAY(sa.String(length=255)), nullable=True))
    op.add_column("groups", sa.Column("leader_list", postgresql.ARRAY(sa.String(length=255)), nullable=True))
    op.execute(
        """
        UPDATE groups g SET
            leader_list = (
                SELECT array_agg(ga.user_id ORDER BY ga.create_time) FROM group_account ga
                WHERE ga.group_id = g.group_id AND ga.is_delete = false AND ga.group_role::text = 'LEADER'
            ),
            member_list = (
                SELECT array_agg(ga.user_id ORDER BY ga.create_time) FROM group_account ga
                WHERE ga.group_id = g.group_id AND ga.is_delete = false AND ga.group_role::text <> 'LEADER'
            )
        """
    )
    op.execute(
        """
        UPDATE accounts a SET group_list = (
            SELECT array_agg(ga.group_id ORDER BY ga.create_time) FROM group_account ga
            WHERE ga.user_id = a.user_id AND ga.is_delete = false
        )
        """
    )
    # 舊版申請中的群組不建 group_account，改回只記在 leader_list
    op.execute(
        """
        DELETE FROM group_account ga USING groups g
        WHERE ga.group_id = g.group_id AND g.status::text <> 'VERIFIED'
        """
    )

    # 6. 外鍵、索引、唯一約束
    op.drop_index("uq_group_account_active", table_name="group_account")
    op.drop_index(op.f("ix_group_account_user_id"), table_name="group_account")
    op.drop_index(op.f("ix_group_account_group_id"), table_name="group_account")
    op.drop_constraint("fk_group_account_user_id", "group_account", type_="foreignkey")
    op.drop_constraint("fk_group_account_group_id", "group_account", type_="foreignkey")

    # 2. 專案擁有者
    op.drop_constraint("ck_project_single_owner", "projects", type_="check")
    op.alter_column("projects", "owner_id", nullable=False)
    op.drop_constraint("fk_projects_created_by", "projects", type_="foreignkey")
    op.drop_column("projects", "created_by")
    op.drop_index(op.f("ix_projects_group_id"), table_name="projects")
    op.drop_constraint("fk_projects_group_id", "projects", type_="foreignkey")
    op.drop_column("projects", "group_id")

    # 1. 編輯者、檢視者都還原成舊的 MEMBER
    op.execute(
        """
        ALTER TABLE group_account
        ALTER COLUMN group_role TYPE role
        USING (CASE WHEN group_role::text = 'LEADER' THEN 'LEADER' ELSE 'MEMBER' END)::role
        """
    )
    group_role_enum.drop(op.get_bind(), checkfirst=True)
