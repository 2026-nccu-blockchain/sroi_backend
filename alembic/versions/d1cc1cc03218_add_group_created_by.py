"""add group created_by

Revision ID: d1cc1cc03218
Revises: 7c504421e473
Create Date: 2026-11-08 03:15:45.750717

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1cc1cc03218'
down_revision: Union[str, None] = '7c504421e473'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAME = "fk_groups_created_by_accounts"


def upgrade() -> None:
    op.add_column('groups', sa.Column('created_by', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_groups_created_by'), 'groups', ['created_by'], unique=False)
    op.create_foreign_key(FK_NAME, 'groups', 'accounts', ['created_by'], ['user_id'])

    # 回填舊群組：建立群組時申請人會在同一筆交易成為組長，之後才可能邀請其他人，
    # 所以每個群組最早的成員紀錄（含軟刪除）就是建立者；沒有任何成員紀錄的群組維持空值
    op.execute(
        """
        UPDATE groups AS g
        SET created_by = first_member.user_id
        FROM (
            SELECT DISTINCT ON (group_id) group_id, user_id
            FROM group_account
            ORDER BY group_id, create_time, uuid
        ) AS first_member
        WHERE g.group_id = first_member.group_id
          AND g.created_by IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, 'groups', type_='foreignkey')
    op.drop_index(op.f('ix_groups_created_by'), table_name='groups')
    op.drop_column('groups', 'created_by')
