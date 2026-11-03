import asyncio
import collections
import logging
from typing import Any, Deque, Optional, Tuple

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

from config import settings

logger = logging.getLogger("telegram_forwarder")

class TelegramForwarderService:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.target_entity_cache: Any = None
        self.recent_msg_ids: Deque[Tuple[int, int]] = collections.deque(maxlen=1000)
        self.is_running: bool = False
        self.is_connected: bool = False

    async def initialize(self):
        """Initialize client connection using TG_SESSION_STRING."""
        if not settings.TG_API_ID or not settings.TG_API_HASH:
            logger.error("TG_API_ID or TG_API_HASH is missing. Please set them in Render environment variables.")
            return

        if not settings.TG_SESSION_STRING or not settings.TG_SESSION_STRING.strip():
            logger.error("TG_SESSION_STRING is missing! Generate it locally using 'python generate_session.py' and add to Render environment variables.")
            return

        session = StringSession(settings.TG_SESSION_STRING.strip())
        self.client = TelegramClient(session, int(settings.TG_API_ID), str(settings.TG_API_HASH))

        try:
            await self.client.connect()
            if await self.client.is_user_authorized():
                self.is_connected = True
                me = await self.client.get_me()
                logger.info(f"Telegram authorized as {me.first_name} (@{me.username or 'none'}) [ID: {me.id}]")
                await self.start_forwarding_listener()
            else:
                logger.error("Session in TG_SESSION_STRING is expired or invalid. Please re-run generate_session.py.")
        except Exception as e:
            logger.exception(f"Failed to connect to Telegram: {e}")

    async def resolve_target_entity(self):
        """Resolve and cache destination entity @V_C_0_3."""
        if self.target_entity_cache:
            return self.target_entity_cache
            
        try:
            entity = await self.client.get_input_entity(settings.FORWARD_TO_USERNAME)
            self.target_entity_cache = entity
            logger.info(f"Resolved destination user {settings.FORWARD_TO_USERNAME} successfully.")
            return entity
        except Exception as e:
            logger.error(f"Failed to resolve recipient {settings.FORWARD_TO_USERNAME}: {e}")
            return None

    def is_target_group(self, chat_id: int, chat_title: Optional[str]) -> bool:
        if settings.TARGET_GROUP_ID is not None and chat_id == settings.TARGET_GROUP_ID:
            return True
            
        if chat_title and settings.TARGET_GROUP_NAME:
            clean_target = settings.TARGET_GROUP_NAME.strip().lower()
            clean_chat = chat_title.strip().lower()
            if clean_target == clean_chat:
                return True
                
        return False

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
            if dedup_key in self.recent_msg_ids:
                return
            self.recent_msg_ids.append(dedup_key)

            snippet = (msg.text or "[Media/Attachment]")[:60].replace("\n", " ")
            logger.info(f"[MATCH] Incoming message {msg.id} in '{chat_title}': '{snippet}'")

            target_entity = await self.resolve_target_entity()
            if not target_entity:
                logger.error(f"Cannot forward: recipient {settings.FORWARD_TO_USERNAME} could not be resolved.")
                return

            try:
                await self.client.forward_messages(entity=target_entity, messages=msg)
                logger.info(f"[SUCCESS] Forwarded message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
            except errors.ChatForwardsRestrictedError:
                if settings.FALLBACK_COPY_ON_RESTRICTED:
                    logger.warning(f"Forwarding restricted in '{chat_title}'. Falling back to direct copy.")
                    await self.client.send_message(
                        entity=target_entity,
                        message=msg.text,
                        file=msg.media,
                        formatting_entities=msg.entities
                    )
                    logger.info(f"[SUCCESS] Copied protected message {msg.id} to {settings.FORWARD_TO_USERNAME}.")
                else:
                    raise
        except Exception as e:
            logger.exception(f"Error processing message: {e}")

    async def start_forwarding_listener(self):
        if self.is_running or not self.client:
            return
            
        self.client.add_event_handler(self.handle_new_message, events.NewMessage(incoming=True))
        self.is_running = True
        logger.info(f"Forwarding listener ACTIVE. Monitoring '{settings.TARGET_GROUP_NAME}' -> forwarding to {settings.FORWARD_TO_USERNAME}.")

    async def shutdown(self):
        if self.client:
            try:
                await self.client.disconnect()
                logger.info("Telegram client disconnected cleanly.")
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")

service = TelegramForwarderService()
