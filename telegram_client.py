import asyncio
import collections
import io
import logging
from typing import Any, Deque, Optional, Tuple

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerSelf, MessageMediaWebPage, MessageMediaEmpty

from config import settings

logger = logging.getLogger("telegram_forwarder")

class TelegramForwarderService:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.target_entity_cache: Any = None
        self.me_id: Optional[int] = None
        self.recent_msg_ids: Deque[Tuple[int, int]] = collections.deque(maxlen=1000)
        self._dedup_set: set[Tuple[int, int]] = set()
        self.is_running: bool = False
        self.is_connected: bool = False
        self._resolve_lock: asyncio.Lock = asyncio.Lock()

    def is_healthy(self) -> bool:
        """Return True if service is actively running and client is connected."""
        connected = bool(self.client and self.client.is_connected() and self.is_connected)
        return self.is_running and connected

    def get_status(self) -> dict:
        """Return a dictionary reflecting live operational health."""
        connected = bool(self.client and self.client.is_connected() and self.is_connected)
        status_str = "ok" if (self.is_running and connected) else ("degraded" if self.is_running else "disconnected")
        ipv6_active = bool(self.client and getattr(self.client, '_use_ipv6', False)) if self.client else settings.use_ipv6
        return {
            "status": status_str,
            "running": self.is_running,
            "connected": connected,
            "ipv6": ipv6_active
        }

    async def initialize(self):
        """Initialize client connection using TG_SESSION_STRING."""
        if not settings.TG_API_ID or not settings.TG_API_HASH:
            logger.error("TG_API_ID or TG_API_HASH is missing. Please set them in environment variables.")
            self.is_connected = False
            self.is_running = False
            return

        if not settings.TG_SESSION_STRING or not settings.TG_SESSION_STRING.strip():
            logger.error("TG_SESSION_STRING is missing! Generate it locally using 'python generate_session.py' and set in environment variables.")
            self.is_connected = False
            self.is_running = False
            return

        try:
            session = StringSession(settings.TG_SESSION_STRING.strip())
            use_ipv6 = settings.use_ipv6
            logger.info(f"Initializing TelegramClient (use_ipv6={use_ipv6})...")
            self.client = TelegramClient(
                session,
                int(settings.TG_API_ID),
                str(settings.TG_API_HASH),
                use_ipv6=use_ipv6
            )
        except Exception as e:
            logger.error(f"Failed to initialize Telethon StringSession or client: {e}")
            self.is_connected = False
            self.is_running = False
            return

        try:
            await self.client.connect()
            if await self.client.is_user_authorized():
                self.is_connected = True
                me = await self.client.get_me()
                self.me_id = getattr(me, 'id', None)
                logger.info(f"Telegram authorized as {me.first_name} (@{me.username or 'none'}) [ID: {me.id}]")
                await self.resolve_target_entity()
                await self.start_forwarding_listener()
            else:
                self.is_connected = False
                logger.error("Session in TG_SESSION_STRING is expired or invalid. Please re-run generate_session.py.")
        except Exception as e:
            self.is_connected = False
            logger.exception(f"Failed to connect to Telegram: {e}")

    async def resolve_target_entity(self):
        """Resolve and cache destination entity configured in FORWARD_TO_USERNAME."""
        if self.target_entity_cache is not None:
            return self.target_entity_cache

        if not self.client:
            logger.error("Client is not initialized; cannot resolve target entity.")
            return None

        if not settings.FORWARD_TO_USERNAME or not settings.FORWARD_TO_USERNAME.strip():
            logger.error("FORWARD_TO_USERNAME is not configured; cannot resolve target entity.")
            return None

        async with self._resolve_lock:
            if self.target_entity_cache is not None:
                return self.target_entity_cache

            target = settings.FORWARD_TO_USERNAME.strip()

            try:
                # Convert valid numeric strings to int so Telethon resolves as numeric entity ID
                if (target.startswith("-") and target[1:].isdigit()) or target.isdigit():
                    target_entity_input: Any = int(target)
                else:
                    target_entity_input = target

                entity = await self.client.get_input_entity(target_entity_input)
                self.target_entity_cache = entity
                logger.info(f"Resolved destination recipient {settings.FORWARD_TO_USERNAME} successfully.")
                return entity
            except Exception as e:
                logger.error(f"Failed to resolve recipient {settings.FORWARD_TO_USERNAME}: {e}")
                return None

    def _matches_group_id(self, configured_id: int, incoming_id: int) -> bool:
        """Compare group IDs with support for Telegram channel -100 prefix and basic chat variants."""
        try:
            c_id = int(configured_id)
            i_id = int(incoming_id)
        except (ValueError, TypeError):
            return False

        if c_id == i_id:
            return True

        # Telegram supergroup/channel marked ID is -(1000000000000 + bare_channel_id)
        CHANNEL_OFFSET = 1000000000000
        if i_id > 0 and c_id == -(CHANNEL_OFFSET + i_id):
            return True
        if c_id > 0 and i_id == -(CHANNEL_OFFSET + c_id):
            return True

        # Telegram basic chat marked ID is -chat_id where chat_id > 0
        if c_id == -i_id:
            return True

        return False

    def is_target_group(self, chat_id: int, chat_title: Optional[str]) -> bool:
        """Check whether incoming chat matches target configuration.
        
        Strict precedence: If TARGET_GROUP_ID is set, only match ID.
        Never fall through to title check when TARGET_GROUP_ID is configured.
        """
        if settings.TARGET_GROUP_ID is not None:
            return self._matches_group_id(settings.TARGET_GROUP_ID, chat_id)
            
        if chat_title and settings.TARGET_GROUP_NAME:
            clean_target = settings.TARGET_GROUP_NAME.strip().lower()
            clean_chat = chat_title.strip().lower()
            if clean_target == clean_chat:
                return True
                
        return False

    def _record_dedup(self, dedup_key: Tuple[int, int]):
        """Record deduplication key in bounded deque and set."""
        if len(self.recent_msg_ids) == self.recent_msg_ids.maxlen:
            oldest = self.recent_msg_ids.popleft()
            self._dedup_set.discard(oldest)
        self.recent_msg_ids.append(dedup_key)
        self._dedup_set.add(dedup_key)

    def _is_deduped(self, dedup_key: Tuple[int, int]) -> bool:
        """Check if message key was previously processed successfully."""
        return dedup_key in self._dedup_set or dedup_key in self.recent_msg_ids

    async def _copy_restricted_message(self, target_entity: Any, msg: Any, chat_title: Optional[str]) -> bool:
        """Copy restricted message text and media when forwarding is disabled."""
        media_to_send = msg.media
        # MessageMediaWebPage is not an InputMedia; omit file so link preview generates naturally
        if isinstance(media_to_send, (MessageMediaWebPage, MessageMediaEmpty)):
            media_to_send = None

        if not msg.text and media_to_send is None:
            logger.warning(f"Message {msg.id} has neither text nor attachable media. Skipping copy.")
            return False

        try:
            await self.client.send_message(
                entity=target_entity,
                message=msg.text,
                file=media_to_send,
                formatting_entities=msg.entities
            )
            logger.info(f"[SUCCESS] Copied protected message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
            return True
        except (errors.ChatForwardsRestrictedError, errors.RPCError, TypeError) as copy_err:
            if media_to_send is not None and hasattr(msg, "download_media"):
                try:
                    logger.info(f"Direct media attach failed ({copy_err}); attempting in-memory download.")
                    media_bytes = await msg.download_media(file=bytes)
                    if media_bytes:
                        buf = io.BytesIO(media_bytes)
                        buf.name = getattr(getattr(msg, "file", None), "name", "media") or "media"
                        await self.client.send_message(
                            entity=target_entity,
                            message=msg.text,
                            file=buf,
                            formatting_entities=msg.entities
                        )
                        logger.info(f"[SUCCESS] Copied downloaded media for message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                        return True
                    elif msg.text:
                        await self.client.send_message(
                            entity=target_entity,
                            message=msg.text,
                            formatting_entities=msg.entities
                        )
                        logger.info(f"[SUCCESS] Copied text for message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                        return True
                except Exception as dl_err:
                    logger.error(f"In-memory media download copy failed: {dl_err}")
                    if msg.text:
                        await self.client.send_message(
                            entity=target_entity,
                            message=msg.text,
                            formatting_entities=msg.entities
                        )
                        logger.info(f"[SUCCESS] Copied text after media failure for message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                        return True
                    raise
            elif msg.text:
                await self.client.send_message(
                    entity=target_entity,
                    message=msg.text,
                    formatting_entities=msg.entities
                )
                logger.info(f"[SUCCESS] Copied text for message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                return True
            else:
                raise

    def _extract_entity_id(self, entity: Any) -> Optional[int]:
        """Extract numeric ID from Telethon entity, InputPeer, or mock."""
        if entity is None:
            return None
        # Handle InputPeerSelf ('me' / 'self' Saved Messages)
        if isinstance(entity, InputPeerSelf) or type(entity).__name__ == "InputPeerSelf":
            return self.me_id
        for attr in ("id", "channel_id", "user_id", "chat_id"):
            val = getattr(entity, attr, None)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and (val.isdigit() or (val.startswith("-") and val[1:].isdigit())):
                return int(val)
        return None

    async def handle_new_message(self, event):
        """Process incoming messages and forward matching ones."""
        try:
            msg = event.message
            if not msg:
                return

            chat = await event.get_chat()
            chat_title = getattr(chat, 'title', None)
            chat_id = event.chat_id

            if not self.is_target_group(chat_id, chat_title):
                return

            dedup_key = (chat_id, msg.id)
            if self._is_deduped(dedup_key):
                logger.debug(f"Message {msg.id} in chat {chat_id} already forwarded. Skipping.")
                return

            # Sanitize logging: log metadata at INFO, snippets at DEBUG
            media_desc = type(msg.media).__name__ if msg.media else "text-only"
            sender_id = getattr(msg, "sender_id", "unknown")
            logger.info(f"[MATCH] Incoming message {msg.id} (sender={sender_id}, type={media_desc}) in '{chat_title}'")
            logger.debug(f"[MATCH DETAIL] Snippet for message {msg.id}: '{(msg.text or '')[:40]}...'")

            target_entity = await self.resolve_target_entity()
            if not target_entity:
                logger.error(f"Cannot forward: recipient {settings.FORWARD_TO_USERNAME} could not be resolved.")
                return

            # Prevent self-loop forwarding
            target_id = self._extract_entity_id(target_entity)
            if target_id is not None and self._matches_group_id(target_id, chat_id):
                logger.warning(
                    f"Source chat ID {chat_id} is identical to destination entity ID {target_id}. Aborting to avoid self-loop."
                )
                return

            max_retries = 3
            success = False
            for attempt in range(max_retries + 1):
                try:
                    try:
                        await self.client.forward_messages(entity=target_entity, messages=msg)
                        logger.info(f"[SUCCESS] Forwarded message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                        success = True
                        break
                    except errors.ChatForwardsRestrictedError:
                        if settings.FALLBACK_COPY_ON_RESTRICTED:
                            logger.warning(f"Forwarding restricted in '{chat_title}'. Falling back to direct copy.")
                            copied = await self._copy_restricted_message(target_entity, msg, chat_title)
                            success = copied
                            break
                        else:
                            raise
                except errors.FloodWaitError as fwe:
                    wait_time = fwe.seconds
                    logger.warning(
                        f"Telegram FloodWait: must wait {wait_time}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    if attempt < max_retries and wait_time <= 300:
                        await asyncio.sleep(wait_time + 1)
                        continue
                    else:
                        logger.error(f"FloodWait exceeded retry budget or limit ({wait_time}s). Message {msg.id} aborted.")
                        break
                except Exception as send_err:
                    logger.exception(f"Error sending message {msg.id}: {send_err}")
                    break

            # Deduplication key is ONLY recorded AFTER successful forwarding/copying
            if success:
                self._record_dedup(dedup_key)

        except Exception as e:
            logger.exception(f"Error processing message: {e}")

    async def start_forwarding_listener(self):
        if self.is_running or not self.client:
            return
            
        self.client.add_event_handler(self.handle_new_message, events.NewMessage(incoming=True))
        self.is_running = True
        logger.info(f"Forwarding listener ACTIVE. Monitoring '{settings.TARGET_GROUP_NAME}' -> forwarding to {settings.FORWARD_TO_USERNAME}.")

    async def shutdown(self):
        """Disconnect client and reset lifecycle state completely."""
        self.is_running = False
        self.me_id = None
        if self.client:
            try:
                if hasattr(self.client, "remove_event_handler"):
                    self.client.remove_event_handler(self.handle_new_message)
                await self.client.disconnect()
                logger.info("Telegram client disconnected cleanly.")
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")
            finally:
                self.is_connected = False
                self.target_entity_cache = None
                self.client = None
        else:
            self.is_connected = False
            self.target_entity_cache = None

service = TelegramForwarderService()
