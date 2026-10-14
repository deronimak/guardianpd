"""add sms_enabled to schools

Revision ID: 5b8e2f4a9c13
Revises: 3a9d5c1e7b24
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5b8e2f4a9c13'
down_revision: Union[str, None] = '3a9d5c1e7b24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('schools', 'sms_enabled')
