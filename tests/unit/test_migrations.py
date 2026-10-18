import os
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade(tmp_path):
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"
    
    alembic_ini_path = os.path.abspath("src/app/db/alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", os.path.abspath("src/app/db/migrations"))

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "users",
        "vpn_servers",
        "products",
        "orders",
        "subscriptions",
        "provisioning_jobs",
        "notifications",
        "support_tickets",
        "support_messages",
        "audit_events",
    }
    assert expected_tables.issubset(set(tables))

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    tables_after = inspector.get_table_names()
    assert not expected_tables.intersection(set(tables_after))


def test_003_keeps_servers_and_what_points_at_them(tmp_path):
    """003 rebuilds vpn_servers (SQLite can't drop columns). Live rows, and the orders and
    subscriptions that reference them, must come through unchanged, both ways."""
    from sqlalchemy import text

    db_url = f"sqlite:///{tmp_path / 'live.db'}"
    cfg = Config(os.path.abspath("src/app/db/alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.abspath("src/app/db/migrations"))
    command.upgrade(cfg, "002_order_renews_subscription")

    engine = create_engine(db_url)
    now = "2026-10-18 12:00:00.000000"
    ids = {name: f"{n:032x}" for n, name in enumerate(("user", "server", "product", "order", "sub"), 1)}
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, telegram_user_id, is_blocked, created_at, updated_at) "
                       "VALUES (:user, 777, 0, :now, :now)"), {**ids, "now": now})
        c.execute(text("INSERT INTO vpn_servers (id, slug, display_name, country_code, country_name, enabled, "
                       "sort_order, provisioner_type, host, ssh_port, ssh_username, max_active_subscriptions, "
                       "created_at, updated_at) VALUES (:server, 'tr-1', 'Turkey', 'TR', 'Turkey', 1, 0, "
                       "'vpnctl', '100.64.0.2', 22, 'vpn-provisioner', 50, :now, :now)"), {**ids, "now": now})
        c.execute(text("INSERT INTO products (id, code, title, duration_days, device_limit, price_amount, "
                       "price_currency, enabled, sort_order, created_at, updated_at) VALUES "
                       "(:product, 'vpn-1m', '1 Month', 30, 1, 5.00, 'EUR', 1, 0, :now, :now)"), {**ids, "now": now})
        c.execute(text("INSERT INTO orders (id, public_order_code, user_id, vpn_server_id, product_id, "
                       "price_amount_snapshot, currency_snapshot, payment_instructions_snapshot, status, "
                       "created_at, updated_at) VALUES (:order, 'ORD-1', :user, :server, :product, 5.00, 'EUR', "
                       "'Pay', 'fulfilled', :now, :now)"), {**ids, "now": now})
        c.execute(text("INSERT INTO subscriptions (id, user_id, order_id, vpn_server_id, product_id, status, "
                       "peer_external_id, config_delivery_status, config_redelivery_count, starts_at, expires_at, "
                       "created_at, updated_at) VALUES (:sub, :user, :order, :server, :product, 'active', "
                       "'user_777_x_tr-1', 'delivered', 0, :now, :now, :now, :now)"), {**ids, "now": now})

    def check(expect_columns, missing_columns):
        cols = {c["name"] for c in inspect(engine).get_columns("vpn_servers")}
        assert expect_columns <= cols and not (missing_columns & cols)
        with engine.connect() as c:
            row = c.execute(text("SELECT slug, host, enabled, max_active_subscriptions FROM vpn_servers "
                                 "WHERE id = :server"), ids).one()
            assert tuple(row) == ("tr-1", "100.64.0.2", 1, 50)
            joined = c.execute(text("SELECT count(*) FROM subscriptions s JOIN orders o ON s.order_id = o.id "
                                    "JOIN vpn_servers v ON s.vpn_server_id = v.id AND o.vpn_server_id = v.id"))
            assert joined.scalar() == 1
            assert c.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        uniques = inspect(engine).get_indexes("vpn_servers") + inspect(engine).get_unique_constraints("vpn_servers")
        assert any("slug" in u["column_names"] for u in uniques)

    command.upgrade(cfg, "head")
    check({"paused"}, {"ssh_port", "ssh_username"})
    with engine.connect() as c:
        assert c.execute(text("SELECT paused FROM vpn_servers")).scalar() == 0

    command.downgrade(cfg, "002_order_renews_subscription")
    check({"ssh_port", "ssh_username"}, {"paused"})
    with engine.connect() as c:
        assert tuple(c.execute(text("SELECT ssh_port, ssh_username FROM vpn_servers")).one()) == (22, "vpn-provisioner")
