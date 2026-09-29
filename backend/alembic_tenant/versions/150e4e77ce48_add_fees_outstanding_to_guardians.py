"""add fees_outstanding to guardians

Revision ID: 150e4e77ce48
Revises: c309bd135068
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '150e4e77ce48'
down_revision: Union[str, None] = 'c309bd135068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing guardians to "not flagged" — the
    # model's Python-side default=False would only apply to brand-new
    # INSERTs, not the already-enrolled guardians in this tenant DB.
    op.add_column(
        'guardians',
        sa.Column('fees_outstanding', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('guardians', 'fees_outstanding')
