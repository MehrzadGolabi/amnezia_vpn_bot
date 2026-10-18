"""Servers can be paused from /servers; drop the SSH columns

Revision ID: 003_server_pause_drop_ssh
Revises: 002_order_renews_subscription
Create Date: 2026-10-18 20:00:00.000000

The /servers button used to flip `enabled`, which .env overwrites on every start.
It now sets `paused`, which only the button changes. ssh_port and ssh_username
have been unused since vpnctl stopped using SSH.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '003_server_pause_drop_ssh'
down_revision: Union[str, None] = '002_order_renews_subscription'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite can't drop columns in place, so batch mode copies the table.
    with op.batch_alter_table('vpn_servers') as batch:
        batch.add_column(sa.Column('paused', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.drop_column('ssh_port')
        batch.drop_column('ssh_username')


def downgrade() -> None:
    with op.batch_alter_table('vpn_servers') as batch:
        batch.add_column(sa.Column('ssh_username', sa.String(length=64), nullable=False,
                                   server_default='vpn-provisioner'))
        batch.add_column(sa.Column('ssh_port', sa.Integer(), nullable=False, server_default='22'))
        batch.drop_column('paused')
