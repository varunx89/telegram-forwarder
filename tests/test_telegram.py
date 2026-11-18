import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from telethon import errors
from telethon.tl.types import InputPeerSelf, MessageMediaWebPage, MessageMediaEmpty, WebPageEmpty

from config import settings
from telegram_client import TelegramForwarderService

@pytest.fixture
def service():
    srv = TelegramForwarderService()
    srv.client = MagicMock()
    srv.client.is_connected = MagicMock(return_value=True)
    return srv

# ============================================================================
# Target Group Matching Tests (VULN-05)
# ============================================================================

def test_is_target_group_by_title(service):
    """Verify group title matching when TARGET_GROUP_ID is None."""
    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "TARGET_GROUP_NAME", "Premium Membership Group"):
        assert service.is_target_group(12345, "Premium Membership Group") is True
        assert service.is_target_group(12345, "  premium membership group  ") is True
        assert service.is_target_group(12345, "PREMIUM MEMBERSHIP GROUP") is True
        assert service.is_target_group(12345, "Random Group") is False
        assert service.is_target_group(12345, None) is False

def test_is_target_group_strict_id_precedence(service):
    """Verify TARGET_GROUP_ID strict matching does NOT fall through to title check (VULN-05)."""
    with patch.object(settings, "TARGET_GROUP_ID", -1001234567890), \
         patch.object(settings, "TARGET_GROUP_NAME", "Premium Membership Group"):
        # Exactly matching ID matches regardless of title
        assert service.is_target_group(-1001234567890, "Any Title") is True
        assert service.is_target_group(-1001234567890, None) is True

        # Bare ID format vs -100 prefix matches
        assert service.is_target_group(1234567890, "Any Title") is True

        # Different chat ID with MATCHING title MUST return False (no spoofing fallthrough!)
        assert service.is_target_group(-1009999999999, "Premium Membership Group") is False
        assert service.is_target_group(-1009999999999, "Other Title") is False

def test_matches_group_id_accurate_supergroup_and_basic_chat(service):
    """Verify _matches_group_id does not falsely match small chat IDs (CHALLENGE-01)."""
    # 555 vs -100555 must NOT collide (naive removeprefix("-100") bug)
    assert service._matches_group_id(555, -100555) is False
    assert service._matches_group_id(-100555, 555) is False

    # Legitimate channel marked ID vs bare ID:
    # Telegram channel marked IDs are -(1000000000000 + bare_id)
    assert service._matches_group_id(1234567890, -1001234567890) is True
    assert service._matches_group_id(-1001234567890, 1234567890) is True

    # Telegram basic group chat marked ID is -chat_id vs bare chat_id
    assert service._matches_group_id(9876543, -9876543) is True
    assert service._matches_group_id(-9876543, 9876543) is True

    # Exact matches
    assert service._matches_group_id(555, 555) is True
    assert service._matches_group_id(-100555, -100555) is True

    # Non-matching distinct channels
    assert service._matches_group_id(-1001234567890, -1009876543210) is False

    # Invalid input types handled gracefully
    assert service._matches_group_id("invalid", 123) is False
    assert service._matches_group_id(123, None) is False

# ============================================================================
# Destination Entity Resolution Tests (VULN-07, VULN-08)
# ============================================================================

@pytest.mark.asyncio
async def test_resolve_target_entity_caching(service):
    """Verify destination entity resolution caches result and avoids repeated RPCs."""
    target_mock = MagicMock()
    service.client.get_input_entity = AsyncMock(return_value=target_mock)

    with patch.object(settings, "FORWARD_TO_USERNAME", "@test_recipient"):
        entity1 = await service.resolve_target_entity()
        assert entity1 == target_mock
        assert service.client.get_input_entity.call_count == 1

        # Second call returns from cache
        entity2 = await service.resolve_target_entity()
        assert entity2 == target_mock
        assert service.client.get_input_entity.call_count == 1

@pytest.mark.asyncio
async def test_resolve_target_entity_numeric_id_converted_to_int(service):
    """Verify numeric string usernames are passed as integers to Telethon (VULN-08)."""
    target_mock = MagicMock()
    service.client.get_input_entity = AsyncMock(return_value=target_mock)

    with patch.object(settings, "FORWARD_TO_USERNAME", "-1001234567890"):
        entity = await service.resolve_target_entity()
        assert entity == target_mock
        service.client.get_input_entity.assert_awaited_once_with(-1001234567890)

@pytest.mark.asyncio
async def test_resolve_target_entity_concurrent_safety(service):
    """Verify resolve_target_entity is thread-safe under concurrent message bursts (VULN-07)."""
    target_mock = MagicMock()

    async def delayed_resolve(arg):
        await asyncio.sleep(0.01)
        return target_mock

    service.client.get_input_entity = AsyncMock(side_effect=delayed_resolve)

    with patch.object(settings, "FORWARD_TO_USERNAME", "@burst_user"):
        # Run 10 concurrent resolution requests
        results = await asyncio.gather(*(service.resolve_target_entity() for _ in range(10)))
        for r in results:
            assert r == target_mock
        # The underlying RPC should only be executed once due to asyncio.Lock
        assert service.client.get_input_entity.call_count == 1

@pytest.mark.asyncio
async def test_resolve_target_entity_unconfigured(service):
    """Verify resolve_target_entity returns None when FORWARD_TO_USERNAME is empty."""
    with patch.object(settings, "FORWARD_TO_USERNAME", ""):
        assert await service.resolve_target_entity() is None

@pytest.mark.asyncio
async def test_resolve_target_entity_malformed_numeric_returns_none_without_crash(service):
    """Verify malformed numeric destination does not raise uncaught ValueError (CHALLENGE-02)."""
    service.client.get_input_entity = AsyncMock(side_effect=ValueError("Cannot find entity"))
    with patch.object(settings, "FORWARD_TO_USERNAME", "--100"):
        res = await service.resolve_target_entity()
        assert res is None

# ============================================================================
# Message Forwarding & Filtering Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_new_message_matching_group(service):
    target_mock = MagicMock()
    target_mock.id = 999999
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 101
    mock_msg.text = "Hello VIP members!"
    mock_msg.media = None
    mock_msg.entities = None
    mock_msg.sender_id = 55555

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "TARGET_GROUP_NAME", "Premium Membership Group"):
        await service.handle_new_message(mock_event)

    service.client.forward_messages.assert_awaited_once_with(
        entity=target_mock,
        messages=mock_msg
    )
    assert service._is_deduped((-100123456, 101))

@pytest.mark.asyncio
async def test_handle_new_message_non_matching_group(service):
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Random Discussion"

    mock_msg = MagicMock()
    mock_msg.id = 102
    mock_msg.text = "Ignore this"

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100987654
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "TARGET_GROUP_NAME", "Premium Membership Group"):
        await service.handle_new_message(mock_event)

    service.client.forward_messages.assert_not_called()

# ============================================================================
# Deduplication & Error Retry Tests (VULN-06)
# ============================================================================

@pytest.mark.asyncio
async def test_handle_new_message_deduplication(service):
    """Verify that messages forwarded successfully are not forwarded a second time."""
    target_mock = MagicMock()
    target_mock.id = 888888
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 200
    mock_msg.text = "Duplicate check message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None):
        # First send
        await service.handle_new_message(mock_event)
        assert service.client.forward_messages.call_count == 1

        # Second send: should be deduplicated
        await service.handle_new_message(mock_event)
        assert service.client.forward_messages.call_count == 1

@pytest.mark.asyncio
async def test_failed_forward_is_not_deduplicated_allows_retry(service):
    """Verify failed forwarding does not prematurely register deduplication key (VULN-06)."""
    target_mock = MagicMock()
    target_mock.id = 777777
    service.resolve_target_entity = AsyncMock(return_value=target_mock)

    # First attempt fails with transient network error
    service.client.forward_messages = AsyncMock(side_effect=[Exception("Network glitch"), None])

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 205
    mock_msg.text = "Retriable message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None):
        # Attempt 1 fails
        await service.handle_new_message(mock_event)
        # Message was NOT added to deduplication cache!
        assert not service._is_deduped((-100123456, 205))

        # Attempt 2 succeeds
        await service.handle_new_message(mock_event)
        assert service.client.forward_messages.call_count == 2
        # Now it IS deduplicated
        assert service._is_deduped((-100123456, 205))

# ============================================================================
# Self-Loop Forwarding Protection Tests (VULN-14)
# ============================================================================

@pytest.mark.asyncio
async def test_prevent_self_loop_forwarding(service):
    """Verify incoming messages from destination chat are aborted to prevent loops (VULN-14)."""
    target_mock = MagicMock()
    target_mock.id = -100123456
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 300
    mock_msg.text = "Self message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    # chat_id is identical to target_mock.id
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None):
        await service.handle_new_message(mock_event)

    # Should not forward
    service.client.forward_messages.assert_not_called()

def test_extract_entity_id_input_peer_self(service):
    """Verify _extract_entity_id correctly extracts self.me_id for InputPeerSelf (CHALLENGE-03)."""
    peer_self = InputPeerSelf()
    assert service._extract_entity_id(peer_self) is None

    service.me_id = 11223344
    assert service._extract_entity_id(peer_self) == 11223344

@pytest.mark.asyncio
async def test_self_loop_protection_with_input_peer_self(service):
    """Verify self-loop protection blocks forwarding to InputPeerSelf when source chat matches me_id (CHALLENGE-03)."""
    service.me_id = 11223344
    service.resolve_target_entity = AsyncMock(return_value=InputPeerSelf())
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Saved Messages"

    mock_msg = MagicMock()
    mock_msg.id = 301
    mock_msg.text = "Loop check message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    # chat_id matches the user's own ID
    mock_event.chat_id = 11223344
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "TARGET_GROUP_NAME", "Saved Messages"):
        await service.handle_new_message(mock_event)

    # Must abort and NOT forward to avoid loop
    service.client.forward_messages.assert_not_called()

@pytest.mark.asyncio
async def test_forwarding_to_input_peer_self_allowed_for_different_chat(service):
    """Verify forwarding to InputPeerSelf succeeds when incoming chat is a monitored channel (CHALLENGE-03)."""
    service.me_id = 11223344
    peer_self = InputPeerSelf()
    service.resolve_target_entity = AsyncMock(return_value=peer_self)
    service.client.forward_messages = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 302
    mock_msg.text = "Legitimate VIP message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -1001234567890
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", -1001234567890):
        await service.handle_new_message(mock_event)

    # Should forward to peer_self
    service.client.forward_messages.assert_awaited_once_with(
        entity=peer_self,
        messages=mock_msg
    )

# ============================================================================
# Restricted Content Fallback & WebPage Link Previews Tests (VULN-02)
# ============================================================================

@pytest.mark.asyncio
async def test_fallback_copy_on_restricted_standard(service):
    """Verify standard fallback copy on ChatForwardsRestrictedError."""
    target_mock = MagicMock()
    target_mock.id = 999999
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock(side_effect=errors.ChatForwardsRestrictedError(request=MagicMock()))
    service.client.send_message = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 401
    mock_msg.text = "Restricted VIP Post"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "FALLBACK_COPY_ON_RESTRICTED", True):
        await service.handle_new_message(mock_event)

    service.client.send_message.assert_awaited_once_with(
        entity=target_mock,
        message="Restricted VIP Post",
        file=None,
        formatting_entities=None
    )
    assert service._is_deduped((-100123456, 401))

@pytest.mark.asyncio
async def test_fallback_copy_with_webpage_media_does_not_crash(service):
    """Verify MessageMediaWebPage has file=None so Telethon does not raise TypeError (VULN-02)."""
    target_mock = MagicMock()
    target_mock.id = 999999
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock(side_effect=errors.ChatForwardsRestrictedError(request=MagicMock()))
    service.client.send_message = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    # Message contains a link with a web page preview
    mock_msg = MagicMock()
    mock_msg.id = 402
    mock_msg.text = "Check out https://news.example.com"
    mock_msg.media = MessageMediaWebPage(webpage=WebPageEmpty(id=1, url=None))
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "FALLBACK_COPY_ON_RESTRICTED", True):
        await service.handle_new_message(mock_event)

    # file should be stripped to None so Telegram generates the web preview naturally
    service.client.send_message.assert_awaited_once_with(
        entity=target_mock,
        message="Check out https://news.example.com",
        file=None,
        formatting_entities=None
    )
    assert service._is_deduped((-100123456, 402))

@pytest.mark.asyncio
async def test_fallback_copy_empty_text_and_empty_media_skips_safely(service):
    """Verify service/empty message with no text or media is skipped gracefully."""
    target_mock = MagicMock()
    target_mock.id = 999999
    service.resolve_target_entity = AsyncMock(return_value=target_mock)
    service.client.forward_messages = AsyncMock(side_effect=errors.ChatForwardsRestrictedError(request=MagicMock()))
    service.client.send_message = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 403
    mock_msg.text = ""
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch.object(settings, "FALLBACK_COPY_ON_RESTRICTED", True):
        await service.handle_new_message(mock_event)

    # send_message should not be called with completely empty content
    service.client.send_message.assert_not_called()

# ============================================================================
# FloodWait Rate Limiting Tests (VULN-03)
# ============================================================================

@pytest.mark.asyncio
async def test_flood_wait_retries_and_succeeds(service):
    """Verify FloodWaitError triggers backoff sleep and subsequent retry succeeds (VULN-03)."""
    target_mock = MagicMock()
    target_mock.id = 999999
    service.resolve_target_entity = AsyncMock(return_value=target_mock)

    # First call raises FloodWaitError(seconds=1), second call succeeds
    flood_error = errors.FloodWaitError(request=MagicMock())
    flood_error.seconds = 1
    service.client.forward_messages = AsyncMock(side_effect=[flood_error, None])

    mock_chat = MagicMock()
    mock_chat.title = "Premium Membership Group"

    mock_msg = MagicMock()
    mock_msg.id = 501
    mock_msg.text = "Rate limited message"
    mock_msg.media = None
    mock_msg.entities = None

    mock_event = MagicMock()
    mock_event.message = mock_msg
    mock_event.chat_id = -100123456
    mock_event.get_chat = AsyncMock(return_value=mock_chat)

    with patch.object(settings, "TARGET_GROUP_ID", None), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await service.handle_new_message(mock_event)

        # Verified backoff sleep was invoked with flood_error.seconds + 1
        mock_sleep.assert_awaited_once_with(2)
        # Message was retried and forwarded
        assert service.client.forward_messages.call_count == 2
        # Message was deduplicated after success
        assert service._is_deduped((-100123456, 501))

# ============================================================================
# Lifecycle and Shutdown Tests (VULN-04, VULN-09)
# ============================================================================

@pytest.mark.asyncio
async def test_initialize_missing_credentials_fails_gracefully(service):
    """Verify initialize handles missing credentials without uncaught exceptions."""
    with patch.object(settings, "TG_API_ID", None):
        await service.initialize()
        assert service.is_connected is False
        assert service.is_running is False
        assert service.is_healthy() is False

@pytest.mark.asyncio
async def test_initialize_malformed_session_string_fails_gracefully(service):
    """Verify initialize catches ValueError on malformed StringSession (VULN-09)."""
    with patch.object(settings, "TG_API_ID", 12345), \
         patch.object(settings, "TG_API_HASH", "valid_hash"), \
         patch.object(settings, "TG_SESSION_STRING", "NOT_A_VALID_BASE64_SESSION_###"):
        await service.initialize()
        assert service.is_connected is False
        assert service.is_running is False
        assert service.is_healthy() is False

@pytest.mark.asyncio
async def test_shutdown_resets_lifecycle_completely(service):
    """Verify shutdown disconnects client, removes handlers, and resets flags (VULN-09)."""
    mock_client = MagicMock()
    mock_client.disconnect = AsyncMock()
    mock_client.remove_event_handler = MagicMock()
    service.client = mock_client
    service.is_running = True
    service.is_connected = True
    service.me_id = 998877
    service.target_entity_cache = "something"

    await service.shutdown()

    assert service.is_running is False
    assert service.is_connected is False
    assert service.target_entity_cache is None
    assert service.me_id is None
    assert service.client is None
    mock_client.disconnect.assert_awaited_once()

@pytest.mark.asyncio
async def test_initialize_success_caches_me_id(service):
    """Verify initialize retrieves and caches me.id for loop detection (CHALLENGE-03)."""
    mock_me = MagicMock()
    mock_me.id = 55443322
    mock_me.first_name = "BotUser"
    mock_me.username = "botuser"

    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.get_me = AsyncMock(return_value=mock_me)
    mock_client.add_event_handler = MagicMock()

    with patch.object(settings, "TG_API_ID", 12345), \
         patch.object(settings, "TG_API_HASH", "valid_hash"), \
         patch.object(settings, "TG_SESSION_STRING", "1BJWvalid_session_string"), \
         patch("telegram_client.StringSession", return_value=MagicMock()), \
         patch("telegram_client.TelegramClient", return_value=mock_client) as mock_tg_constructor, \
         patch.object(service, "resolve_target_entity", new=AsyncMock()), \
         patch.object(service, "start_forwarding_listener", new=AsyncMock()):
        await service.initialize()
        assert service.is_connected is True
        assert service.me_id == 55443322
        mock_tg_constructor.assert_called_once()
        _, kwargs = mock_tg_constructor.call_args
        assert kwargs.get("use_ipv6") is True

@pytest.mark.asyncio
async def test_initialize_respects_ipv6_disabled_flag(service):
    """Verify initialize passes use_ipv6=False when explicitly configured."""
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.get_me = AsyncMock(return_value=MagicMock(id=111, first_name="Test", username="test"))
    mock_client.add_event_handler = MagicMock()

    with patch.object(settings, "TG_API_ID", 12345), \
         patch.object(settings, "TG_API_HASH", "valid_hash"), \
         patch.object(settings, "TG_SESSION_STRING", "1BJWvalid_session_string"), \
         patch.object(settings, "TG_USE_IPV6", False), \
         patch("telegram_client.StringSession", return_value=MagicMock()), \
         patch("telegram_client.TelegramClient", return_value=mock_client) as mock_tg_constructor, \
         patch.object(service, "resolve_target_entity", new=AsyncMock()), \
         patch.object(service, "start_forwarding_listener", new=AsyncMock()):
        await service.initialize()
        _, kwargs = mock_tg_constructor.call_args
        assert kwargs.get("use_ipv6") is False

def test_get_status_includes_ipv6_metric(service):
    """Verify get_status reports ipv6 state accurately."""
    mock_client = MagicMock()
    mock_client.is_connected = MagicMock(return_value=True)
    mock_client._use_ipv6 = True

    with patch.object(service, "client", mock_client), \
         patch.object(service, "is_running", True), \
         patch.object(service, "is_connected", True):
        status = service.get_status()
        assert status["status"] == "ok"
        assert status["ipv6"] is True
