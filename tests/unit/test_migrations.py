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
