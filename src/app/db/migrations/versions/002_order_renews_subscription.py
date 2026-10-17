"""Orders can renew an existing subscription

Revision ID: 002_order_renews_subscription
Revises: 001_initial_schema
Create Date: 2026-10-17 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '002_order_renews_subscription'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('orders') as batch:
        batch.add_column(sa.Column('renews_subscription_id', sa.Uuid(), nullable=True))
        batch.create_index('ix_orders_renews_subscription_id', ['renews_subscription_id'])


def downgrade() -> None:
    with op.batch_alter_table('orders') as batch:
        batch.drop_index('ix_orders_renews_subscription_id')
        batch.drop_column('renews_subscription_id')
