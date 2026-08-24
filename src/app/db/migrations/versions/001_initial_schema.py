"""Initial database schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-24 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('language_code', sa.String(length=10), nullable=True),
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_telegram_user_id'), 'users', ['telegram_user_id'], unique=True)

    # VPN Servers table
    op.create_table(
        'vpn_servers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('country_code', sa.String(length=8), nullable=False),
        sa.Column('country_name', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provisioner_type', sa.String(length=32), nullable=False, server_default='mock'),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('ssh_port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('ssh_username', sa.String(length=64), nullable=False, server_default='vpn-provisioner'),
        sa.Column('max_active_subscriptions', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_vpn_servers_slug'), 'vpn_servers', ['slug'], unique=True)

    # Products table
    op.create_table(
        'products',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('device_limit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('price_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('price_currency', sa.String(length=8), nullable=False, server_default='EUR'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_products_code'), 'products', ['code'], unique=True)

    # Orders table
    op.create_table(
        'orders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('public_order_code', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('vpn_server_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('price_amount_snapshot', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency_snapshot', sa.String(length=8), nullable=False),
        sa.Column('payment_instructions_snapshot', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('receipt_telegram_file_id', sa.String(length=255), nullable=True),
        sa.Column('receipt_message_id', sa.BigInteger(), nullable=True),
        sa.Column('receipt_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('receipt_media_type', sa.String(length=32), nullable=True),
        sa.Column('receipt_note', sa.Text(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vpn_server_id'], ['vpn_servers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orders_public_order_code'), 'orders', ['public_order_code'], unique=True)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)

    # Subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('vpn_server_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('peer_external_id', sa.String(length=128), nullable=True),
        sa.Column('peer_label', sa.String(length=128), nullable=True),
        sa.Column('config_delivery_status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('config_delivery_message_id', sa.BigInteger(), nullable=True),
        sa.Column('config_redelivery_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vpn_server_id'], ['vpn_servers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
    )
    op.create_index(op.f('ix_subscriptions_expires_at'), 'subscriptions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_subscriptions_peer_external_id'), 'subscriptions', ['peer_external_id'], unique=True)
    op.create_index(op.f('ix_subscriptions_status'), 'subscriptions', ['status'], unique=False)
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)

    # Provisioning jobs table
    op.create_table(
        'provisioning_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('job_type', sa.String(length=32), nullable=False),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False),
        sa.Column('aggregate_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_by', sa.String(length=128), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_provisioning_jobs_aggregate_id'), 'provisioning_jobs', ['aggregate_id'], unique=False)
    op.create_index(op.f('ix_provisioning_jobs_available_at'), 'provisioning_jobs', ['available_at'], unique=False)
    op.create_index(op.f('ix_provisioning_jobs_job_type'), 'provisioning_jobs', ['job_type'], unique=False)
    op.create_index(op.f('ix_provisioning_jobs_status'), 'provisioning_jobs', ['status'], unique=False)

    # Notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('subscription_id', sa.Uuid(), nullable=True),
        sa.Column('notification_type', sa.String(length=32), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_idempotency_key'), 'notifications', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)

    # Support tickets table
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('public_ticket_code', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('assigned_admin_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_tickets_public_ticket_code'), 'support_tickets', ['public_ticket_code'], unique=True)
    op.create_index(op.f('ix_support_tickets_status'), 'support_tickets', ['status'], unique=False)
    op.create_index(op.f('ix_support_tickets_user_id'), 'support_tickets', ['user_id'], unique=False)

    # Support messages table
    op.create_table(
        'support_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ticket_id', sa.Uuid(), nullable=False),
        sa.Column('sender_type', sa.String(length=32), nullable=False),
        sa.Column('sender_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('attachment_file_id', sa.String(length=255), nullable=True),
        sa.Column('attachment_type', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_messages_ticket_id'), 'support_messages', ['ticket_id'], unique=False)

    # Audit events table
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('actor_type', sa.String(length=32), nullable=False),
        sa.Column('actor_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.Uuid(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_events_actor_telegram_user_id'), 'audit_events', ['actor_telegram_user_id'], unique=False)
    op.create_index(op.f('ix_audit_events_actor_type'), 'audit_events', ['actor_type'], unique=False)
    op.create_index(op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_events_entity_id'), 'audit_events', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_events_entity_type'), 'audit_events', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_events_event_type'), 'audit_events', ['event_type'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_events')
    op.drop_table('support_messages')
    op.drop_table('support_tickets')
    op.drop_table('notifications')
    op.drop_table('provisioning_jobs')
    op.drop_table('subscriptions')
    op.drop_table('orders')
    op.drop_table('products')
    op.drop_table('vpn_servers')
    op.drop_table('users')
