"""add student_credentials, student photo, and make attendance_events.guardian_id nullable

Revision ID: 7c2e91d4b0a8
Revises: 150e4e77ce48
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '7c2e91d4b0a8'
down_revision: Union[str, None] = '150e4e77ce48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('print_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_printed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['student_id'], ['students.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.add_column('students', sa.Column('photo', sa.LargeBinary(), nullable=True))
    # Pupil-card scans have no guardian involved. Dropping NOT NULL is safe
    # for every existing row (they all already have one).
    op.alter_column('attendance_events', 'guardian_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    op.alter_column('attendance_events', 'guardian_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column('students', 'photo')
    op.drop_table('student_credentials')
