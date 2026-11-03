import os
import secrets
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram Credentials
    # API ID and Hash can be obtained from https://my.telegram.org
    TG_API_ID: Optional[int] = Field(default=None, description="Telegram API ID from my.telegram.org")
    TG_API_HASH: Optional[str] = Field(default=None, description="Telegram API Hash from my.telegram.org")
    TG_PHONE: Optional[str] = Field(default=None, description="Default phone number with country code e.g. +1234567890")
    
    # Telethon Session Persistence
    # If TG_SESSION_STRING is provided (e.g. copied from Web UI into Render Env Vars),
    # it will be preferred. Otherwise, sqlite session file at TG_SESSION_NAME will be used.
    TG_SESSION_STRING: Optional[str] = Field(default=None, description="Telethon StringSession data")
    TG_SESSION_NAME: str = Field(default="data/telegram_session", description="Path/name for SQLite session file")
    
    # Forwarding Criteria
    TARGET_GROUP_NAME: str = Field(default="Premium Membership Group", description="Name of the source group to monitor")
    TARGET_GROUP_ID: Optional[int] = Field(default=None, description="Exact Telegram Chat ID of source group if known")
    FORWARD_TO_USERNAME: str = Field(default="@V_C_0_3", description="Recipient Telegram username or ID")
    
    # Web Dashboard Security
    ADMIN_PASSWORD: str = Field(default="admin-secret-replace-me", description="Password required to access browser login and dashboard")
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_hex(32), description="Session secret for auth cookies")
    COOKIE_NAME: str = Field(default="tg_fwd_session", description="Auth cookie name")
    
    # Server Bind & Logging
    HOST: str = Field(default="0.0.0.0", description="HTTP server bind host")
    PORT: int = Field(default=10000, description="HTTP server port (Render default is 10000 or $PORT)")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    MAX_LOG_ENTRIES: int = Field(default=200, description="Max activity entries to retain in-memory")
    
    # Restrict forwards fallback (copy message if forwarding is restricted)
    FALLBACK_COPY_ON_RESTRICTED: bool = Field(default=True, description="Copy text/media directly if group disables message forwarding")

    @field_validator("FORWARD_TO_USERNAME")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("@") and not v.startswith("-") and not v.isdigit():
            return f"@{v}"
        return v

# Global settings instance
settings = Settings()
