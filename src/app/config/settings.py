import re
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProvisionerMode(str, Enum):
    MOCK = "mock"
    SSH = "ssh"


class ServerConfig(BaseModel):
    slug: str
    enabled: bool = True
    country_code: str
    display_name: str
    host: str = "localhost"
    port: int = 22
    username: str = "vpn-provisioner"
    ssh_private_key_path: Optional[str] = None
    ssh_known_hosts_path: Optional[str] = None
    max_active_subscriptions: Optional[int] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=True,
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("mock_token_123456")
    ADMIN_TELEGRAM_IDS: Union[List[int], str] = Field(default_factory=list)
    ADMIN_CHAT_ID: int = 0

    DATABASE_URL: SecretStr = SecretStr("postgresql+asyncpg://vpn_bot:vpn_bot@postgres:5432/vpn_bot")

    PROVISIONER_MODE: ProvisionerMode = ProvisionerMode.MOCK
    PROVISIONING_JOB_POLL_SECONDS: int = 5
    EXPIRY_CHECK_INTERVAL_SECONDS: int = 300
    REMINDER_DAYS_BEFORE_EXPIRY: Union[List[int], str] = Field(default_factory=lambda: [7, 3, 1])
    CONFIG_REDELIVERY_LIMIT: int = 3
    PEER_REMOVAL_GRACE_DAYS: int = 30

    PAYMENT_INSTRUCTIONS_EN: str = "Please transfer payment to the account and upload your receipt photo/document."
    PAYMENT_INSTRUCTIONS_FA: str = "لطفا هزینه را واریز نموده و تصویر یا فایل رسید را ارسال کنید."

    vpn_servers: Dict[str, ServerConfig] = Field(default_factory=dict)

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_admin_telegram_ids(cls, v: Any) -> List[int]:
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return [int(p) for p in parts]
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return []

    @field_validator("REMINDER_DAYS_BEFORE_EXPIRY", mode="before")
    @classmethod
    def parse_reminder_days(cls, v: Any) -> List[int]:
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return [int(p) for p in parts]
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return [7, 3, 1]

    @field_validator("PROVISIONER_MODE", mode="before")
    @classmethod
    def parse_provisioner_mode(cls, v: Any) -> ProvisionerMode:
        if isinstance(v, str):
            return ProvisionerMode(v.lower())
        return v

    @model_validator(mode="before")
    @classmethod
    def extract_vpn_servers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        vpn_servers: Dict[str, Dict[str, Any]] = {}
        prefix = "VPN_SERVER_"
        for key, value in list(data.items()):
            if key.startswith(prefix):
                rest = key[len(prefix):]
                parts = rest.split("_")
                for i in range(1, len(parts)):
                    candidate_slug = "_".join(parts[:i]).lower().replace("_", "-")
                    field_name = "_".join(parts[i:]).lower()
                    if field_name in {
                        "enabled", "slug", "country_code", "display_name",
                        "host", "port", "username", "ssh_private_key_path",
                        "ssh_known_hosts_path", "max_active_subscriptions"
                    }:
                        server_dict = vpn_servers.setdefault(candidate_slug, {"slug": candidate_slug})
                        if field_name == "enabled":
                            server_dict[field_name] = str(value).lower() in ("true", "1", "yes")
                        elif field_name == "port":
                            server_dict[field_name] = int(value) if value else 22
                        elif field_name == "max_active_subscriptions":
                            server_dict[field_name] = int(value) if value else None
                        else:
                            server_dict[field_name] = value
                        break

        final_servers: Dict[str, ServerConfig] = {}
        for temp_slug, s_data in vpn_servers.items():
            slug = s_data.get("slug", temp_slug)
            if "country_code" in s_data and "display_name" in s_data:
                final_servers[slug] = ServerConfig(**s_data)

        existing = data.get("vpn_servers", {})
        if isinstance(existing, dict):
            final_servers.update(existing)

        data["vpn_servers"] = final_servers
        return data

    def __repr__(self) -> str:
        return (
            f"Settings(APP_ENV={self.APP_ENV!r}, LOG_LEVEL={self.LOG_LEVEL!r}, "
            f"PROVISIONER_MODE={self.PROVISIONER_MODE!r}, "
            f"ADMIN_TELEGRAM_IDS={self.ADMIN_TELEGRAM_IDS!r}, "
            f"ADMIN_CHAT_ID={self.ADMIN_CHAT_ID!r}, "
            f"servers={list(self.vpn_servers.keys())})"
        )


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
