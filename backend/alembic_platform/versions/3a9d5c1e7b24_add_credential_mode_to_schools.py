"""add credential_mode to schools

Revision ID: 3a9d5c1e7b24
Revises: 14a4727cc947
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a9d5c1e7b24'
down_revision: Union[str, None] = '14a4727cc947'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills every already-enrolled school to "guardian"
    # (today's behavior) — pupil mode is strictly opt-in per school.
    op.add_column(
        'schools',
        sa.Column('credential_mode', sa.String(length=20), nullable=False, server_default='guardian'),
    )


def downgrade() -> None:
    op.drop_column('schools', 'credential_mode')
