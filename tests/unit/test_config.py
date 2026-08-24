import pytest
from pydantic import ValidationError
from src.app.config.settings import Settings, ServerConfig, ProvisionerMode


def test_default_settings():
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        ADMIN_TELEGRAM_IDS=[123456789, 987654321],
        ADMIN_CHAT_ID=-1001234567890,
        DATABASE_URL="postgresql+asyncpg://vpn_bot:vpn_bot@postgres:5432/vpn_bot",
        LOG_LEVEL="INFO",
    )
    assert settings.APP_ENV == "development"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.PROVISIONER_MODE == ProvisionerMode.MOCK
    assert settings.ADMIN_TELEGRAM_IDS == [123456789, 987654321]
    assert settings.ADMIN_CHAT_ID == -1001234567890
    assert settings.REMINDER_DAYS_BEFORE_EXPIRY == [7, 3, 1]
    assert settings.CONFIG_REDELIVERY_LIMIT == 3


def test_admin_ids_parsing_from_string():
    settings = Settings(
        TELEGRAM_BOT_TOKEN="dummy_token",
        ADMIN_TELEGRAM_IDS="111, 222 , 333",
        ADMIN_CHAT_ID=-1001234567890,
        DATABASE_URL="postgresql+asyncpg://vpn_bot:vpn_bot@postgres:5432/vpn_bot",
    )
    assert settings.ADMIN_TELEGRAM_IDS == [111, 222, 333]


def test_reminder_days_parsing_from_string():
    settings = Settings(
        TELEGRAM_BOT_TOKEN="dummy_token",
        ADMIN_TELEGRAM_IDS=[111],
        ADMIN_CHAT_ID=-100,
        DATABASE_URL="postgresql+asyncpg://vpn_bot:vpn_bot@postgres:5432/vpn_bot",
        REMINDER_DAYS_BEFORE_EXPIRY="14, 7, 3, 1",
    )
    assert settings.REMINDER_DAYS_BEFORE_EXPIRY == [14, 7, 3, 1]


def test_vpn_servers_parsing_from_env():
    env_data = {
        "TELEGRAM_BOT_TOKEN": "token",
        "ADMIN_TELEGRAM_IDS": "123",
        "ADMIN_CHAT_ID": "-100",
        "DATABASE_URL": "postgresql+asyncpg://vpn_bot:vpn_bot@postgres:5432/vpn_bot",
        "VPN_SERVER_DE_1_ENABLED": "true",
        "VPN_SERVER_DE_1_SLUG": "de-1",
        "VPN_SERVER_DE_1_COUNTRY_CODE": "DE",
        "VPN_SERVER_DE_1_DISPLAY_NAME": "Germany Frankfurt",
        "VPN_SERVER_DE_1_HOST": "de1.example.com",
        "VPN_SERVER_DE_1_PORT": "22",
        "VPN_SERVER_DE_1_USERNAME": "vpn-provisioner",
        "VPN_SERVER_DE_1_SSH_PRIVATE_KEY_PATH": "/run/secrets/de_1_key",
        "VPN_SERVER_DE_1_SSH_KNOWN_HOSTS_PATH": "/run/secrets/known_hosts",
        "VPN_SERVER_DE_1_MAX_ACTIVE_SUBSCRIPTIONS": "100",
    }
    settings = Settings(**env_data)
    assert "de-1" in settings.vpn_servers
    server = settings.vpn_servers["de-1"]
    assert server.enabled is True
    assert server.slug == "de-1"
    assert server.country_code == "DE"
    assert server.display_name == "Germany Frankfurt"
    assert server.host == "de1.example.com"
    assert server.port == 22
    assert server.username == "vpn-provisioner"
    assert server.max_active_subscriptions == 100


def test_secret_redaction_in_repr():
    settings = Settings(
        TELEGRAM_BOT_TOKEN="super_secret_bot_token",
        ADMIN_TELEGRAM_IDS=[123456],
        ADMIN_CHAT_ID=-100,
        DATABASE_URL="postgresql+asyncpg://vpn_bot:secret_pass@postgres:5432/vpn_bot",
    )
    rep = repr(settings)
    assert "super_secret_bot_token" not in rep
    assert "secret_pass" not in rep
