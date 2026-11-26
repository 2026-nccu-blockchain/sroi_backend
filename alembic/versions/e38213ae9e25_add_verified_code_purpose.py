"""add verified code purpose

Revision ID: e38213ae9e25
Revises: 23c27bd0024d
Create Date: 2026-11-25 02:10:57.866131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e38213ae9e25'
down_revision: Union[str, None] = '23c27bd0024d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 只保留這次的欄位；autogenerate 另外偵測到 consent_records 唯一約束、forms.status 型別、
    # project_outcomes 索引的差異，那些是既有的 model / 資料庫落差，不在這次處理
    # server_default register：既有的驗證碼都是註冊用的
    op.add_column('verified_codes', sa.Column('purpose', sa.String(length=20), server_default='register', nullable=False))


def downgrade() -> None:
    op.drop_column('verified_codes', 'purpose')
