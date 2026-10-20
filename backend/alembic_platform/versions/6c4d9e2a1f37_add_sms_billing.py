"""add per-SMS pricing to subscriptions and SMS usage lines to invoices

Revision ID: 6c4d9e2a1f37
Revises: 5b8e2f4a9c13
Create Date: 2026-10-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6c4d9e2a1f37'
down_revision: Union[str, None] = '5b8e2f4a9c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('price_per_sms_naira', sa.Numeric(8, 2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('sms_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('price_per_sms_naira', sa.Numeric(8, 2), nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('sms_amount_naira', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('invoices', 'sms_amount_naira')
    op.drop_column('invoices', 'price_per_sms_naira')
    op.drop_column('invoices', 'sms_count')
    op.drop_column('subscriptions', 'price_per_sms_naira')
