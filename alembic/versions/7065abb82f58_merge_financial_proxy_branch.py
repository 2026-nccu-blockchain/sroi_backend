"""merge financial proxy branch

Revision ID: 7065abb82f58
Revises: 4623db3d045d, 9d5e6f7a8b01
Create Date: 2026-10-28 18:41:52.239622

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7065abb82f58'
down_revision: Union[str, None] = ('4623db3d045d', '9d5e6f7a8b01')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
