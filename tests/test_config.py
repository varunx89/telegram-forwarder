import pytest
from pydantic import ValidationError
from config import Settings

def test_default_config():
    """Verify default configuration without hardcoded personal credentials."""
    cfg = Settings(_env_file=None)
    assert cfg.TARGET_GROUP_NAME == "Premium Membership Group"
    assert cfg.TARGET_GROUP_ID is None
    assert cfg.FORWARD_TO_USERNAME == ""
    assert cfg.HOST == "::"
    assert cfg.PORT == 10000
    assert cfg.FALLBACK_COPY_ON_RESTRICTED is True
    assert cfg.LOG_LEVEL == "INFO"
    assert cfg.USE_IPV6 is True
    assert cfg.TG_USE_IPV6 is None
    assert cfg.use_ipv6 is True

def test_username_normalization():
    """Verify FORWARD_TO_USERNAME normalizer handles all valid Telegram identifier types."""
    # Alphanumeric username without @ prefix should get @ added
    cfg1 = Settings(_env_file=None, FORWARD_TO_USERNAME="test_recipient")
    assert cfg1.FORWARD_TO_USERNAME == "@test_recipient"

    # Username with @ prefix should remain intact
    cfg2 = Settings(_env_file=None, FORWARD_TO_USERNAME="@test_recipient")
    assert cfg2.FORWARD_TO_USERNAME == "@test_recipient"

    # Negative channel / supergroup ID should remain numeric string
    cfg3 = Settings(_env_file=None, FORWARD_TO_USERNAME="-1001234567890")
    assert cfg3.FORWARD_TO_USERNAME == "-1001234567890"

    # Positive user ID should remain numeric string
    cfg4 = Settings(_env_file=None, FORWARD_TO_USERNAME="987654321")
    assert cfg4.FORWARD_TO_USERNAME == "987654321"

    # Phone number with + prefix should remain intact
    cfg5 = Settings(_env_file=None, FORWARD_TO_USERNAME="+12345678901")
    assert cfg5.FORWARD_TO_USERNAME == "+12345678901"

    # Telethon keywords 'me' and 'self' (for Saved Messages) should be preserved
    cfg6 = Settings(_env_file=None, FORWARD_TO_USERNAME="me")
    assert cfg6.FORWARD_TO_USERNAME == "me"

    cfg7 = Settings(_env_file=None, FORWARD_TO_USERNAME="SELF")
    assert cfg7.FORWARD_TO_USERNAME == "self"

    # Empty string should be preserved
    cfg8 = Settings(_env_file=None, FORWARD_TO_USERNAME="")
    assert cfg8.FORWARD_TO_USERNAME == ""

    cfg9 = Settings(_env_file=None, FORWARD_TO_USERNAME="   ")
    assert cfg9.FORWARD_TO_USERNAME == ""

def test_username_normalization_invalid():
    """Verify invalid usernames like solitary '@' raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, FORWARD_TO_USERNAME="@")
    assert "cannot be solely '@'" in str(exc_info.value)

def test_username_normalization_invalid_hyphens_and_signs():
    """Verify malformed numeric IDs with multiple hyphens or invalid signs raise ValidationError (CHALLENGE-02)."""
    invalid_inputs = ["--100", "---123", "-+100", "-abc", "--", "+1234abc", "+"]
    for bad_input in invalid_inputs:
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, FORWARD_TO_USERNAME=bad_input)
        err_msg = str(exc_info.value)
        assert ("Invalid FORWARD_TO_USERNAME" in err_msg or "cannot be solely" in err_msg)

def test_ipv6_configuration_options():
    """Verify USE_IPV6 and TG_USE_IPV6 overrides and effective use_ipv6 property."""
    # Explicitly disabled
    cfg1 = Settings(_env_file=None, USE_IPV6=False)
    assert cfg1.USE_IPV6 is False
    assert cfg1.use_ipv6 is False

    # General disabled, but TG_USE_IPV6 explicitly enabled
    cfg2 = Settings(_env_file=None, USE_IPV6=False, TG_USE_IPV6=True)
    assert cfg2.USE_IPV6 is False
    assert cfg2.TG_USE_IPV6 is True
    assert cfg2.use_ipv6 is True

    # General enabled, but TG_USE_IPV6 explicitly disabled
    cfg3 = Settings(_env_file=None, USE_IPV6=True, TG_USE_IPV6=False)
    assert cfg3.USE_IPV6 is True
    assert cfg3.TG_USE_IPV6 is False
    assert cfg3.use_ipv6 is False

    # IPv4 host binding override
    cfg4 = Settings(_env_file=None, HOST="0.0.0.0")
    assert cfg4.HOST == "0.0.0.0"

def test_custom_config():
    """Verify custom settings overrides are properly loaded."""
    cfg = Settings(
        _env_file=None,
        TG_API_ID=99999,
        TG_API_HASH="fakehash123",
        TG_SESSION_STRING="fakesession",
        TARGET_GROUP_NAME="VIP Signals",
        TARGET_GROUP_ID=-1009876543210,
        FORWARD_TO_USERNAME="vip_destination",
        FALLBACK_COPY_ON_RESTRICTED=False,
        PORT=8080,
        LOG_LEVEL="DEBUG"
    )
    assert cfg.TG_API_ID == 99999
    assert cfg.TG_API_HASH == "fakehash123"
    assert cfg.TG_SESSION_STRING == "fakesession"
    assert cfg.TARGET_GROUP_NAME == "VIP Signals"
    assert cfg.TARGET_GROUP_ID == -1009876543210
    assert cfg.FORWARD_TO_USERNAME == "@vip_destination"
    assert cfg.FALLBACK_COPY_ON_RESTRICTED is False
    assert cfg.PORT == 8080
    assert cfg.LOG_LEVEL == "DEBUG"
