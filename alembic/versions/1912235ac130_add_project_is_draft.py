"""add project is_draft

Revision ID: 1912235ac130
Revises: d9e0f1a2b3c4
Create Date: 2026-11-24 17:39:28.116075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1912235ac130'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 只保留這次的欄位；autogenerate 另外偵測到 consent_records 唯一約束、forms.status 型別、
    # project_outcomes 索引的差異，那些是既有的 model / 資料庫落差，不在這次處理
    # server_default false：既有專案（含既有群組專案）都視為公開，組員照樣看得到
    op.add_column('projects', sa.Column('is_draft', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('projects', 'is_draft')
