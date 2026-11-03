import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon import errors
from telethon.sessions import StringSession

from telegram_client import TelegramForwarderService

@pytest.fixture
def auth_service():
    srv = TelegramForwarderService()
    srv.client = MagicMock()
    srv.client.session = StringSession()
    return srv

@pytest.mark.asyncio
async def test_send_code_success(auth_service):
    sent_code_mock = MagicMock()
    sent_code_mock.phone_code_hash = "mock_hash_12345"
    auth_service.client.send_code_request = AsyncMock(return_value=sent_code_mock)

    result = await auth_service.send_code("+1234567890")

    assert result["success"] is True
    assert auth_service.auth_state == "PENDING_CODE"
    assert auth_service.phone_code_hash == "mock_hash_12345"
    assert auth_service.pending_phone == "+1234567890"
    auth_service.client.send_code_request.assert_awaited_once_with("+1234567890")

@pytest.mark.asyncio
async def test_verify_code_success(auth_service):
    auth_service.pending_phone = "+1234567890"
    auth_service.phone_code_hash = "mock_hash_12345"
    auth_service.auth_state = "PENDING_CODE"

    me_mock = MagicMock()
    me_mock.id = 99999
    me_mock.first_name = "Alice"
    me_mock.username = "alice_tg"
    
    auth_service.client.sign_in = AsyncMock()
    auth_service.client.get_me = AsyncMock(return_value=me_mock)
    auth_service.start_forwarding_listener = AsyncMock()

    result = await auth_service.verify_code("12345")

    assert result["success"] is True
    assert result["requires_password"] is False
    assert auth_service.auth_state == "AUTHORIZED"
    assert auth_service.pending_phone is None
    auth_service.client.sign_in.assert_awaited_once_with(
        phone="+1234567890",
        code="12345",
        phone_code_hash="mock_hash_12345"
    )
    auth_service.start_forwarding_listener.assert_awaited_once()

@pytest.mark.asyncio
async def test_verify_code_2fa_needed(auth_service):
    auth_service.pending_phone = "+1234567890"
    auth_service.phone_code_hash = "mock_hash_12345"
    auth_service.auth_state = "PENDING_CODE"

    # Simulate SessionPasswordNeededError
    auth_service.client.sign_in = AsyncMock(side_effect=errors.SessionPasswordNeededError(request=MagicMock()))

    result = await auth_service.verify_code("12345")

    assert result["success"] is False
    assert result["requires_password"] is True
    assert auth_service.auth_state == "PENDING_PASSWORD"
    # Phone and hash are retained to allow 2FA completion
    assert auth_service.pending_phone == "+1234567890"

@pytest.mark.asyncio
async def test_submit_password_success(auth_service):
    auth_service.auth_state = "PENDING_PASSWORD"
    auth_service.pending_phone = "+1234567890"

    me_mock = MagicMock()
    me_mock.id = 99999
    me_mock.first_name = "Alice"
    me_mock.username = "alice_tg"

    auth_service.client.sign_in = AsyncMock()
    auth_service.client.get_me = AsyncMock(return_value=me_mock)
    auth_service.start_forwarding_listener = AsyncMock()

    result = await auth_service.submit_password("my_super_secret_2fa")

    assert result["success"] is True
    assert auth_service.auth_state == "AUTHORIZED"
    auth_service.client.sign_in.assert_awaited_once_with(password="my_super_secret_2fa")
    auth_service.start_forwarding_listener.assert_awaited_once()

@pytest.mark.asyncio
async def test_logout(auth_service):
    auth_service.client.is_user_authorized = AsyncMock(return_value=True)
    auth_service.client.log_out = AsyncMock()
    auth_service.auth_state = "AUTHORIZED"

    result = await auth_service.logout()

    assert result["success"] is True
    assert auth_service.auth_state == "NOT_AUTHORIZED"
    auth_service.client.log_out.assert_awaited_once()
