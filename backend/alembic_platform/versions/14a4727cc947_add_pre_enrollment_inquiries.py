"""add pre_enrollment_inquiries

Revision ID: 14a4727cc947
Revises: b7a1c9e3f402
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '14a4727cc947'
down_revision: Union[str, None] = 'b7a1c9e3f402'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pre_enrollment_inquiries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('school_name', sa.String(length=255), nullable=False),
        sa.Column('school_address', sa.String(length=500), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=False),
        sa.Column('contact_email', sa.String(length=255), nullable=False),
        sa.Column('contact_whatsapp', sa.String(length=30), nullable=False),
        sa.Column('active_parents_estimate', sa.String(length=100), nullable=False),
        sa.Column('desired_enrollment_date', sa.String(length=100), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('pre_enrollment_inquiries')
