"""add logo to schools

Revision ID: b7a1c9e3f402
Revises: 429b4639300a
Create Date: 2026-09-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7a1c9e3f402'
down_revision: Union[str, None] = '429b4639300a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('logo', sa.LargeBinary(), nullable=True))
    op.add_column('schools', sa.Column('logo_content_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'logo_content_type')
    op.drop_column('schools', 'logo')
