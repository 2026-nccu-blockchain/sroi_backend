"""enrollment verification replaces campus id change

Revision ID: 23c27bd0024d
Revises: 1912235ac130
Create Date: 2026-11-24 23:32:09.888453

"""
from typing import Sequence, Union

import re
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '23c27bd0024d'
down_revision: Union[str, None] = '1912235ac130'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 和 app/api/services/enrollment.py 相同的規則；migration 不 import 程式碼，避免之後程式改動影響舊 migration
TAIPEI = timezone(timedelta(hours=8))
STUDENT_ID = re.compile(r"^\d{9}$")


def _initial_due_year(campus_id: str, now: datetime) -> int:
    due = int(campus_id[:3]) + 4
    while now >= datetime(due + 1911, 10, 1, tzinfo=TAIPEI):
        due += 1
    return due


def upgrade() -> None:
    # autogenerate 另外偵測到 consent_records 唯一約束、forms.status 型別、project_outcomes 索引的差異，
    # 那些是既有的 model / 資料庫落差，不在這次處理
    op.create_table('enrollment_verifications',
    sa.Column('verification_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('due_year', sa.Integer(), nullable=False),
    sa.Column('stored_name', sa.String(length=255), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.String(length=36), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_delete', sa.Boolean(), nullable=False),
    sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('update_time', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['reviewed_by'], ['accounts.user_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['accounts.user_id'], ),
    sa.PrimaryKeyConstraint('verification_id')
    )
    op.create_index(op.f('ix_enrollment_verifications_user_id'), 'enrollment_verifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_enrollment_verifications_verification_id'), 'enrollment_verifications', ['verification_id'], unique=False)
    op.drop_index(op.f('ix_verified_in_progress_uuid'), table_name='verified_in_progress')
    op.drop_table('verified_in_progress')
    op.add_column('accounts', sa.Column('verify_due_year', sa.Integer(), nullable=True))
    op.add_column('accounts', sa.Column('delete_reason', sa.String(length=30), nullable=True))

    # 學號改成由 email 前綴決定：9 碼數字才是學生，其餘帳號清成 NULL；學生設定第一次驗證年
    bind = op.get_bind()
    now = datetime.now(TAIPEI)
    accounts = bind.execute(sa.text("SELECT user_id, email FROM accounts")).fetchall()
    for user_id, email in accounts:
        prefix = (email or "").split("@")[0]
        campus_id = prefix if STUDENT_ID.fullmatch(prefix) else None
        bind.execute(
            sa.text("UPDATE accounts SET campus_id = :campus_id, verify_due_year = :due WHERE user_id = :user_id"),
            {
                "campus_id": campus_id,
                "due": _initial_due_year(campus_id, now) if campus_id else None,
                "user_id": user_id,
            },
        )


def downgrade() -> None:
    # 注意：原本透過學號變更申請填的 campus_id 已在 upgrade 清掉，無法還原
    op.drop_column('accounts', 'delete_reason')
    op.drop_column('accounts', 'verify_due_year')
    op.create_table('verified_in_progress',
    sa.Column('uuid', sa.VARCHAR(length=36), autoincrement=False, nullable=False),
    sa.Column('campus_id', sa.VARCHAR(length=36), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.VARCHAR(length=36), autoincrement=False, nullable=False),
    sa.Column('is_delete', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('create_time', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('update_time', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('uuid', name=op.f('verified_in_progress_pkey'))
    )
    op.create_index(op.f('ix_verified_in_progress_uuid'), 'verified_in_progress', ['uuid'], unique=False)
    op.drop_index(op.f('ix_enrollment_verifications_verification_id'), table_name='enrollment_verifications')
    op.drop_index(op.f('ix_enrollment_verifications_user_id'), table_name='enrollment_verifications')
    op.drop_table('enrollment_verifications')
