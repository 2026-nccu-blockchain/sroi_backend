"""external accounts and invitations

Revision ID: 4d7c62529d90
Revises: e38213ae9e25
Create Date: 2026-11-25 03:03:59.252375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d7c62529d90'
down_revision: Union[str, None] = 'e38213ae9e25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # autogenerate 另外偵測到 consent_records 唯一約束、forms.status 型別、project_outcomes 索引的差異，
    # 那些是既有的 model / 資料庫落差，不在這次處理
    op.create_table('external_invitations',
    sa.Column('invitation_id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('organization', sa.String(length=255), nullable=False),
    sa.Column('valid_years', sa.Integer(), nullable=False),
    sa.Column('invited_by', sa.String(length=36), nullable=False),
    sa.Column('token_nonce', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_user_id', sa.String(length=36), nullable=True),
    sa.Column('is_delete', sa.Boolean(), nullable=False),
    sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('update_time', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['accepted_user_id'], ['accounts.user_id'], ),
    sa.ForeignKeyConstraint(['invited_by'], ['accounts.user_id'], ),
    sa.PrimaryKeyConstraint('invitation_id')
    )
    op.create_index(op.f('ix_external_invitations_email'), 'external_invitations', ['email'], unique=False)
    op.create_index(op.f('ix_external_invitations_invitation_id'), 'external_invitations', ['invitation_id'], unique=False)
    # 既有帳號都是政大師生
    op.add_column('accounts', sa.Column('account_type', sa.String(length=20), server_default='nccu', nullable=False))
    op.add_column('accounts', sa.Column('organization', sa.String(length=255), nullable=True))
    op.add_column('accounts', sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'valid_until')
    op.drop_column('accounts', 'organization')
    op.drop_column('accounts', 'account_type')
    op.drop_index(op.f('ix_external_invitations_invitation_id'), table_name='external_invitations')
    op.drop_index(op.f('ix_external_invitations_email'), table_name='external_invitations')
    op.drop_table('external_invitations')
