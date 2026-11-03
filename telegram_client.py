import asyncio
import collections
import datetime
import logging
import os
from typing import Any, Deque, Dict, List, Optional, Tuple

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession, SQLiteSession
from telethon.tl.types import Channel, Chat, User

from config import settings

logger = logging.getLogger("telegram_forwarder")

class TelegramForwarderService:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.auth_state: str = "NOT_AUTHORIZED"  # NOT_AUTHORIZED, PENDING_CODE, PENDING_PASSWORD, AUTHORIZED
        self.pending_phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.target_entity_cache: Any = None
        self.recent_msg_ids: Deque[Tuple[int, int]] = collections.deque(maxlen=1000)
        self.activity_logs: Deque[Dict[str, Any]] = collections.deque(maxlen=settings.MAX_LOG_ENTRIES)
        self._handler_registered: bool = False
        self.resolved_source_chat: Optional[Dict[str, Any]] = None

    def _mask_phone(self, phone: Optional[str]) -> str:
        if not phone: 
            return "N/A"
        p = str(phone).strip()
        if len(p) <= 4:
            return "***"
        return f"{p[:3]}****{p[-2:]}"

    def add_log(self, event_type: str, details: str, status: str = "info", extra: Optional[Dict[str, Any]] = None):
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details,
            "status": status,
            "extra": extra or {}
        }
        self.activity_logs.appendleft(log_entry)
        logger.info(f"[{event_type.upper()}] ({status}): {details}")

    def get_session(self):
        if settings.TG_SESSION_STRING and settings.TG_SESSION_STRING.strip():
            logger.info("Using StringSession from TG_SESSION_STRING environment variable.")
            return StringSession(settings.TG_SESSION_STRING.strip())
        
        # Ensure directory for sqlite session exists
        session_dir = os.path.dirname(settings.TG_SESSION_NAME)
        if session_dir and not os.path.exists(session_dir):
            os.makedirs(session_dir, exist_ok=True)
        
        logger.info(f"Using SQLiteSession at {settings.TG_SESSION_NAME}.")
        return settings.TG_SESSION_NAME

    async def initialize(self):
        """Initialize client connection without blocking for authentication."""
        if not settings.TG_API_ID or not settings.TG_API_HASH:
            self.auth_state = "MISSING_CREDENTIALS"
            self.add_log(
                "init",
                "TG_API_ID or TG_API_HASH is missing. Please configure them in environment variables or .env.",
                status="warning"
            )
            return

        session = self.get_session()
        self.client = TelegramClient(session, int(settings.TG_API_ID), str(settings.TG_API_HASH))
        
        try:
            await self.client.connect()
            if await self.client.is_user_authorized():
                self.auth_state = "AUTHORIZED"
                me = await self.client.get_me()
                username = f"@{me.username}" if me.username else me.first_name
                self.add_log(
                    "auth",
                    f"Already authorized as {username} (ID: {me.id}, Phone: {self._mask_phone(me.phone)})",
                    status="success"
                )
                await self.start_forwarding_listener()
            else:
                self.auth_state = "NOT_AUTHORIZED"
                self.add_log(
                    "auth",
                    "Client connected to Telegram gateway. Waiting for user login via browser.",
                    status="info"
                )
        except Exception as e:
            logger.exception("Failed to connect to Telegram")
            self.auth_state = "ERROR"
            self.add_log("connect_error", f"Connection failed: {str(e)}", status="error")

    async def get_status(self) -> Dict[str, Any]:
        """Return current status for web UI and health checks."""
        user_info = None
        is_auth = False
        session_string = None
        
        if self.client and await self.client.is_user_authorized():
            is_auth = True
            self.auth_state = "AUTHORIZED"
            try:
                me = await self.client.get_me()
                user_info = {
                    "id": me.id,
                    "first_name": me.first_name,
                    "last_name": me.last_name,
                    "username": me.username,
                    "phone": self._mask_phone(me.phone)
                }
                # Export StringSession for easy persistence
                if isinstance(self.client.session, StringSession):
                    session_string = self.client.session.save()
                else:
                    try:
                        # Export StringSession from SQLite
                        temp_str_sess = StringSession()
                        temp_str_sess.set_dc(
                            self.client.session.dc_id,
                            self.client.session.server_address,
                            self.client.session.port
                        )
                        temp_str_sess.auth_key = self.client.session.auth_key
                        session_string = temp_str_sess.save()
                    except Exception:
                        session_string = None
            except Exception as e:
                logger.warning(f"Could not fetch user info: {e}")

        return {
            "state": self.auth_state,
            "is_authorized": is_auth,
            "user": user_info,
            "target_group_name": settings.TARGET_GROUP_NAME,
            "target_group_id": settings.TARGET_GROUP_ID,
            "forward_to": settings.FORWARD_TO_USERNAME,
            "pending_phone": self._mask_phone(self.pending_phone) if self.pending_phone else None,
            "session_string": session_string,
            "has_credentials": bool(settings.TG_API_ID and settings.TG_API_HASH)
        }

    async def send_code(self, phone: str) -> Dict[str, Any]:
        """Step 1 of Web Login: Send verification code to phone number."""
        if not self.client:
            await self.initialize()
            if not self.client:
                return {"success": False, "error": "Telegram client not initialized. Check TG_API_ID and TG_API_HASH."}

        clean_phone = phone.strip().replace(" ", "").replace("-", "")
        if not clean_phone.startswith("+"):
            clean_phone = f"+{clean_phone}"

        try:
            sent_code = await self.client.send_code_request(clean_phone)
            self.pending_phone = clean_phone
            self.phone_code_hash = sent_code.phone_code_hash
            self.auth_state = "PENDING_CODE"
            self.add_log(
                "send_code",
                f"Verification code requested for {self._mask_phone(clean_phone)}.",
                status="info"
            )
            return {
                "success": True,
                "message": f"Verification code sent to {self._mask_phone(clean_phone)}. Please check your Telegram app or SMS.",
                "phone": self._mask_phone(clean_phone),
                "state": self.auth_state
            }
        except errors.FloodWaitError as e:
            msg = f"Telegram rate limit (FloodWait). Please wait {e.seconds} seconds before trying again."
            self.add_log("send_code_error", msg, status="error")
            return {"success": False, "error": msg}
        except Exception as e:
            logger.exception("send_code error")
            self.add_log("send_code_error", str(e), status="error")
            return {"success": False, "error": f"Failed to send code: {str(e)}"}

    async def verify_code(self, code: str) -> Dict[str, Any]:
        """Step 2 of Web Login: Verify 5-digit code."""
        if not self.client or not self.pending_phone or not self.phone_code_hash:
            return {"success": False, "error": "No pending phone verification. Please start with entering your phone number."}

        clean_code = code.strip().replace(" ", "")
        
        try:
            await self.client.sign_in(
                phone=self.pending_phone,
                code=clean_code,
                phone_code_hash=self.phone_code_hash
            )
            # Authorized successfully
            self.auth_state = "AUTHORIZED"
            me = await self.client.get_me()
            self.pending_phone = None
            self.phone_code_hash = None
            
            await self.start_forwarding_listener()
            
            session_str = None
            if hasattr(self.client.session, 'save'):
                session_str = self.client.session.save()
                
            self.add_log(
                "login_success",
                f"Logged in successfully as {me.first_name} (@{me.username or 'none'}).",
                status="success"
            )
            return {
                "success": True,
                "requires_password": False,
                "message": f"Welcome {me.first_name}! Logged in successfully.",
                "session_string": session_str,
                "state": self.auth_state
            }
        except errors.SessionPasswordNeededError:
            self.auth_state = "PENDING_PASSWORD"
            self.add_log(
                "2fa_required",
                "Two-Factor Authentication (Cloud Password) required to complete login.",
                status="warning"
            )
            return {
                "success": False,
                "requires_password": True,
                "message": "Two-Factor Authentication is enabled on your account. Please enter your 2FA Cloud Password.",
                "state": self.auth_state
            }
        except errors.PhoneCodeInvalidError:
            return {"success": False, "error": "Invalid verification code. Please check and try again."}
        except errors.PhoneCodeExpiredError:
            self.auth_state = "NOT_AUTHORIZED"
            return {"success": False, "error": "Verification code expired. Please request a new code."}
        except Exception as e:
            logger.exception("verify_code error")
            return {"success": False, "error": f"Sign-in failed: {str(e)}"}

    async def submit_password(self, password: str) -> Dict[str, Any]:
        """Step 3 (Optional): Submit 2FA Cloud Password."""
        if not self.client or self.auth_state != "PENDING_PASSWORD":
            return {"success": False, "error": "Account is not currently waiting for a 2FA password."}

        try:
            await self.client.sign_in(password=password)
            self.auth_state = "AUTHORIZED"
            me = await self.client.get_me()
            self.pending_phone = None
            self.phone_code_hash = None
            
            await self.start_forwarding_listener()
            
            session_str = None
            if hasattr(self.client.session, 'save'):
                session_str = self.client.session.save()

            self.add_log(
                "2fa_success",
                f"2FA verified. Logged in as {me.first_name} (@{me.username or 'none'}).",
                status="success"
            )
            return {
                "success": True,
                "message": f"Two-Factor authentication verified! Welcome {me.first_name}.",
                "session_string": session_str,
                "state": self.auth_state
            }
        except errors.PasswordHashInvalidError:
            return {"success": False, "error": "Invalid 2FA password. Please try again."}
        except Exception as e:
            logger.exception("submit_password error")
            return {"success": False, "error": f"2FA verification failed: {str(e)}"}

    async def logout(self) -> Dict[str, Any]:
        """Log out and reset state."""
        if self.client and await self.client.is_user_authorized():
            try:
                await self.client.log_out()
            except Exception as e:
                logger.warning(f"Error logging out: {e}")
        
        self.auth_state = "NOT_AUTHORIZED"
        self.pending_phone = None
        self.phone_code_hash = None
        self.target_entity_cache = None
        self._handler_registered = False
        
        # Delete sqlite session if exists
        sqlite_path = f"{settings.TG_SESSION_NAME}.session"
        if os.path.exists(sqlite_path):
            try:
                os.remove(sqlite_path)
            except Exception as e:
                logger.warning(f"Could not remove session file {sqlite_path}: {e}")
                
        self.add_log("logout", "User logged out. Session invalidated.", status="info")
        return {"success": True, "message": "Logged out successfully."}

    async def resolve_target_entity(self):
        """Resolve and cache destination entity @V_C_0_3."""
        if self.target_entity_cache:
            return self.target_entity_cache
            
        try:
            entity = await self.client.get_input_entity(settings.FORWARD_TO_USERNAME)
            self.target_entity_cache = entity
            self.add_log(
                "target_resolved",
                f"Resolved destination user {settings.FORWARD_TO_USERNAME} successfully.",
                status="success"
            )
            return entity
        except Exception as e:
            logger.error(f"Could not resolve target user {settings.FORWARD_TO_USERNAME}: {e}")
            self.add_log(
                "target_resolve_error",
                f"Failed to resolve recipient {settings.FORWARD_TO_USERNAME}: {str(e)}",
                status="error"
            )
            return None

    def is_target_group(self, chat_id: int, chat_title: Optional[str]) -> bool:
        """Check whether the chat matches the specified target group criteria."""
        # If TARGET_GROUP_ID is configured, test exact ID
        if settings.TARGET_GROUP_ID is not None and chat_id == settings.TARGET_GROUP_ID:
            return True
            
        # Match by group title
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

            # Check if source chat matches target group
            if not self.is_target_group(chat_id, chat_title):
                return

            # Deduplication: avoid forwarding same message multiple times
            dedup_key = (chat_id, msg.id)
            if dedup_key in self.recent_msg_ids:
                return
            self.recent_msg_ids.append(dedup_key)

            # Record source info
            self.resolved_source_chat = {
                "id": chat_id,
                "title": chat_title
            }

            snippet = (msg.text or "[Media/Attachment]")[:60].replace("\n", " ")
            self.add_log(
                "message_received",
                f"New message in '{chat_title}' (ID {msg.id}): \"{snippet}\"",
                status="info",
                extra={"chat_id": chat_id, "msg_id": msg.id}
            )

            target_entity = await self.resolve_target_entity()
            if not target_entity:
                self.add_log(
                    "forward_failed",
                    f"Cannot forward message {msg.id}: recipient {settings.FORWARD_TO_USERNAME} not resolved.",
                    status="error"
                )
                return

            # Forward the exact message to @V_C_0_3
            try:
                await self.client.forward_messages(
                    entity=target_entity,
                    messages=msg
                )
                self.add_log(
                    "forward_success",
                    f"Forwarded message {msg.id} to {settings.FORWARD_TO_USERNAME} successfully.",
                    status="success",
                    extra={"chat_id": chat_id, "msg_id": msg.id}
                )
            except errors.ChatForwardsRestrictedError:
                # Group restricts forwarding (protect content). Fallback to direct copy.
                if settings.FALLBACK_COPY_ON_RESTRICTED:
                    logger.warning(f"Forwarding restricted in {chat_title}. Falling back to copying message.")
                    await self.client.send_message(
                        entity=target_entity,
                        message=msg.text,
                        file=msg.media,
                        formatting_entities=msg.entities
                    )
                    self.add_log(
                        "forward_copied",
                        f"Message {msg.id} copied to {settings.FORWARD_TO_USERNAME} (group restricted direct forwarding).",
                        status="warning",
                        extra={"chat_id": chat_id, "msg_id": msg.id}
                    )
                else:
                    raise
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            self.add_log(
                "forward_error",
                f"Error forwarding message: {str(e)}",
                status="error"
            )

    async def start_forwarding_listener(self):
        """Register event handler for incoming messages."""
        if self._handler_registered or not self.client:
            return
            
        self.client.add_event_handler(self.handle_new_message, events.NewMessage(incoming=True))
        self._handler_registered = True
        self.add_log(
            "listener_started",
            f"Forwarding listener active. Monitoring for '{settings.TARGET_GROUP_NAME}' -> forwarding to {settings.FORWARD_TO_USERNAME}.",
            status="success"
        )

    async def shutdown(self):
        """Gracefully disconnect Telethon client."""
        if self.client:
            try:
                await self.client.disconnect()
                self.add_log("shutdown", "Telethon client disconnected.", status="info")
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")

# Global service instance
service = TelegramForwarderService()
