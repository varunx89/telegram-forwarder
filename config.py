import os
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
    FORWARD_TO_USERNAME: str = Field(default="", description="Recipient Telegram username (e.g. @username), user/channel ID, or 'me'")
    
    # Copy message if group disables forwarding
    FALLBACK_COPY_ON_RESTRICTED: bool = Field(default=True, description="Copy text/media directly if group disables message forwarding")

    # Host and port for Render health checks
    # Default '::' binds to IPv6 (all interfaces) and dual-stack on Linux.
    HOST: str = Field(default="::", description="HTTP server bind host (default '::' for IPv6 and dual-stack)")
    PORT: int = Field(default=10000, description="HTTP server port (Render default is 10000 or $PORT)")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # IPv6 & Outbound Networking
    USE_IPV6: bool = Field(default=True, description="Enable IPv6 for Telegram MTProto and outbound connections (essential for IPv6-only environments)")
    TG_USE_IPV6: Optional[bool] = Field(default=None, description="Optional explicit override for Telegram IPv6 setting")

    @property
    def use_ipv6(self) -> bool:
        """Return effective IPv6 boolean (TG_USE_IPV6 override takes precedence if explicitly set)."""
        if self.TG_USE_IPV6 is not None:
            return self.TG_USE_IPV6
        return self.USE_IPV6

    @field_validator("FORWARD_TO_USERNAME")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return ""
        if v == "@":
            raise ValueError("FORWARD_TO_USERNAME cannot be solely '@'")
        # Reject malformed strings with multiple hyphens or invalid signs
        if v.startswith("-"):
            if not (v.startswith("-") and v[1:].isdigit()):
                raise ValueError(f"Invalid FORWARD_TO_USERNAME format: '{v}' (malformed numeric ID or hyphenated prefix)")
            return v
        # Telethon keywords for Saved Messages
        if v.lower() in ("me", "self"):
            return v.lower()
        # Numeric user ID
        if v.isdigit():
            return v
        # International phone number format (e.g. +1234567890)
        if v.startswith("+"):
            if not v[1:].isdigit():
                raise ValueError(f"Invalid FORWARD_TO_USERNAME phone number format: '{v}'")
            return v
        # Telegram username: ensure single '@' prefix
        if not v.startswith("@"):
            return f"@{v}"
        return v

# Global settings instance
settings = Settings()
