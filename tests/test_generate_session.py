from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from generate_session import main as generate_session_main

@pytest.mark.asyncio
async def test_generate_session_empty_credentials():
    """Verify generate_session exits if API_ID or API_HASH is empty."""
    with patch("builtins.input", side_effect=["", ""]), \
         pytest.raises(SystemExit) as exc:
        await generate_session_main()
    assert exc.value.code == 1

@pytest.mark.asyncio
async def test_generate_session_non_int_api_id():
    """Verify generate_session exits if API_ID is not a valid integer."""
    with patch("builtins.input", side_effect=["not_an_int", "valid_hash"]), \
         pytest.raises(SystemExit) as exc:
        await generate_session_main()
    assert exc.value.code == 1

@pytest.mark.asyncio
async def test_generate_session_success():
    """Verify generate_session completes MTProto start and outputs session string."""
    mock_client = MagicMock()
    mock_client.start = AsyncMock()
    mock_user = MagicMock()
    mock_user.first_name = "Alice"
    mock_user.username = "alice_tg"
    mock_user.id = 12345
    mock_client.get_me = AsyncMock(return_value=mock_user)
    mock_client.session.save = MagicMock(return_value="1BVtsOIWbu0...fake_session_string...")
    mock_client.disconnect = AsyncMock()

    with patch("builtins.input", side_effect=["123456", "my_hash"]), \
         patch("generate_session.TelegramClient", return_value=mock_client) as mock_tg_constructor:
        await generate_session_main()

    mock_client.start.assert_awaited_once()
    mock_client.get_me.assert_awaited_once()
    mock_client.session.save.assert_called_once()
    mock_client.disconnect.assert_awaited_once()
    _, kwargs = mock_tg_constructor.call_args
    assert kwargs.get("use_ipv6") is True

@pytest.mark.asyncio
async def test_generate_session_respects_ipv4_flag():
    """Verify generate_session respects --ipv4 argument or environment override."""
    mock_client = MagicMock()
    mock_client.start = AsyncMock()
    mock_client.get_me = AsyncMock(return_value=MagicMock(first_name="Bob", username="bob", id=999))
    mock_client.session.save = MagicMock(return_value="1BVts...mock...")
    mock_client.disconnect = AsyncMock()

    with patch("builtins.input", side_effect=["123456", "my_hash"]), \
         patch.dict("os.environ", {"USE_IPV6": "false"}), \
         patch("generate_session.TelegramClient", return_value=mock_client) as mock_tg_constructor:
        await generate_session_main()

    _, kwargs = mock_tg_constructor.call_args
    assert kwargs.get("use_ipv6") is False
