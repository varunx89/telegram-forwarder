import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from telethon import errors

from config import settings
from telegram_client import TelegramForwarderService

@pytest.fixture
def service():
    srv = TelegramForwarderService()
    srv.client = MagicMock()
    return srv

def test_is_target_group(service):
    # Default target group is 'Premium Membership Group'
    assert service.is_target_group(12345, "Premium Membership Group") is True
    # Case-insensitive and trimmed
    assert service.is_target_group(12345, "  premium membership group  ") is True
    # Non-matching group
    assert service.is_target_group(12345, "Random Group") is False
    assert service.is_target_group(12345, None) is False

def test_is_target_group_with_id(service):
    with patch.object(settings, 'TARGET_GROUP_ID', -100999999):
        assert service.is_target_group(-100999999, "Any Title") is True
        assert service.is_target_group(-100111111, "Other Title") is False

@pytest.mark.asyncio
async def test_handle_new_message_matching_group(service):
    target_mock = MagicMock()
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock()

    # Create mock message event
    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"
    
    mock_msg = MagicMock()
    mock_msg.id = 101
    mock_msg.text = "Hello VIP members!"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    await service.handle_new_message(mock_event)

    # Should forward to target entity
    service.client.forward_messages.assert_awaited_once_with(
        entity=target_mock,
        messages=mock_msg
    )

@pytest.mark.asyncio
async def test_handle_new_message_non_matching_group(service):
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "General Discussion"
    
    mock_msg = MagicMock()
    mock_msg.id = 102
    mock_msg.text = "Not premium"

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100654321
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    await service.handle_new_message(mock_event)

    # Should NOT forward
    service.client.forward_messages.assert_not_called()

@pytest.mark.asyncio
async def test_handle_new_message_deduplication(service):
    target_mock = MagicMock()
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"
    
    mock_msg = MagicMock()
    mock_msg.id = 200
    mock_msg.text = "Duplicate Test Message"

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    # Process first time
    await service.handle_new_message(mock_event)
    assert service.client.forward_messages.call_count == 1

    # Process second time with same chat and msg_id
    await service.handle_new_message(mock_event)
    assert service.client.forward_messages.call_count == 1  # Still 1, deduplicated

@pytest.mark.asyncio
async def test_handle_new_message_fallback_copy_on_restricted(service):
    target_mock = MagicMock()
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    # Simulate ChatForwardsRestrictedError when calling forward_messages
    service.client.forward_messages = AsyncMock(side_effect=errors.ChatForwardsRestrictedError(request=MagicMock()))
    service.client.send_message = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"
    
    mock_msg = MagicMock()
    mock_msg.id = 301
    mock_msg.text = "Protected content in group"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    await service.handle_new_message(mock_event)

    # Forward was attempted
    service.client.forward_messages.assert_awaited_once()
    # Fallback to copy message directly was executed
    service.client.send_message.assert_awaited_once_with(
        entity=target_mock,
        message="Protected content in group",
        file=None,
        formatting_entities=None
    )
