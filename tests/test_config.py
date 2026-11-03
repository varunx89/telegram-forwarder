import pytest
from config import Settings

def test_default_config():
    cfg = Settings(_env_file=None)
    assert cfg.TARGET_GROUP_NAME == "Premium Membership Group"
    assert cfg.FORWARD_TO_USERNAME == "@V_C_0_3"
    assert cfg.HOST == "0.0.0.0"
    assert cfg.PORT == 10000
    assert cfg.FALLBACK_COPY_ON_RESTRICTED is True

def test_username_normalization():
    # Missing @ prefix should be automatically added
    cfg = Settings(_env_file=None, FORWARD_TO_USERNAME="V_C_0_3")
    assert cfg.FORWARD_TO_USERNAME == "@V_C_0_3"

    # Existing @ prefix should remain untouched
    cfg2 = Settings(_env_file=None, FORWARD_TO_USERNAME="@V_C_0_3")
    assert cfg2.FORWARD_TO_USERNAME == "@V_C_0_3"

    # Numeric chat IDs should remain untouched
    cfg3 = Settings(_env_file=None, FORWARD_TO_USERNAME="-100123456")
    assert cfg3.FORWARD_TO_USERNAME == "-100123456"
