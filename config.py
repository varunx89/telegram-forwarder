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
    TG_API_ID: Optional[int] = Field(default=None, description="Telegram API ID from my.telegram.org")
    TG_API_HASH: Optional[str] = Field(default=None, description="Telegram API Hash from my.telegram.org")
    
    # Session String (Required for headless operation)
    TG_SESSION_STRING: Optional[str] = Field(default=None, description="Telethon StringSession data")
    
    # Forwarding Criteria
    TARGET_GROUP_NAME: str = Field(default="Premium Membership Group", description="Name of source group to monitor")
    TARGET_GROUP_ID: Optional[int] = Field(default=None, description="Exact Telegram Chat ID of source group if known")
    FORWARD_TO_USERNAME: str = Field(default="@V_C_0_3", description="Recipient Telegram username or ID")
    
    # Copy message if group disables forwarding
    FALLBACK_COPY_ON_RESTRICTED: bool = Field(default=True, description="Copy text/media directly if group disables message forwarding")

    # Host and port for Render health checks
    HOST: str = Field(default="0.0.0.0", description="HTTP server bind host")
    PORT: int = Field(default=10000, description="HTTP server port (Render default is 10000 or $PORT)")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @field_validator("FORWARD_TO_USERNAME")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("@") and not v.startswith("-") and not v.isdigit():
            return f"@{v}"
        return v

# Global settings instance
settings = Settings()
