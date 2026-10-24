"""bridge the merged group revision used by the shared database

Revision ID: f1a2b3c4d5e6
Revises: 2254ddfe7a5f
Create Date: 2026-10-22

The shared database was stamped with this revision after the group migration
history was consolidated. Its schema already contains every change from
2254ddfe7a5f, so this compatibility revision intentionally performs no DDL.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "2254ddfe7a5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
