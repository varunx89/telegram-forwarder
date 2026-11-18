# Telegram Forwarder Service

A production-ready, secure, containerized Python service built with **Telethon** and **FastAPI** that monitors a designated Telegram group or channel and reliably forwards messages to a configured recipient (user, channel, group, or Saved Messages).

The service runs in a **pure headless architecture** utilizing Telethon's `StringSession`, eliminating the need for interactive terminal access or persistent local disk storage in cloud environments such as **Render**, **AWS**, or **Docker**.

---

## ✨ Key Features & Security Architecture

- **Headless Cloud & IPv6-Native Architecture:** Operates with zero interactive terminal dependencies using an encrypted `TG_SESSION_STRING`. Built with native IPv6 connectivity (`use_ipv6=True`) for MTProto and dual-stack server binding (`HOST=::`), making it fully functional on IPv6-only VMs and cloud instances without outbound IPv4.
- **Strict Group Isolation & Anti-Spoofing:** When `TARGET_GROUP_ID` is configured, incoming messages are strictly validated by numeric chat ID without falling through to title matching, preventing rogue group spoofing.
- **Self-Loop Forwarding Protection:** Automatically detects if the destination recipient matches the source group and aborts forwarding to prevent infinite recursive loops.
- **Restricted Content Copy Fallback:** Automatically detects if the source group has "Restrict saving content" (`ChatForwardsRestrictedError`) enabled. Falls back to copying text, formatted entities, and media directly. Handles web link previews (`MessageMediaWebPage`) cleanly without type errors.
- **Rate-Limit & FloodWait Resilience:** Explicitly catches Telethon `FloodWaitError`, logs the wait duration, performs asynchronous backoff sleep, and retries forwarding without message loss or account ban risks.
- **Reliable Deduplication:** Deduplication keys `(chat_id, message_id)` are recorded in an in-memory O(1) cache only **after** a message has been successfully delivered, guaranteeing automatic retries on transient network errors.
- **Thread-Safe Entity Resolution:** Entity resolution is synchronized via `asyncio.Lock()` to prevent redundant MTProto RPC floods during burst message events.
- **Realistic Cloud Health Probes:** The `/health` endpoint inspects live client connectivity and service state, returning **HTTP 200 OK** only when connected and running, and **HTTP 503 Service Unavailable** when disconnected or degraded. Includes `/live` for container liveness probes.
- **Sensitive Log Sanitization:** Incoming message metadata (message ID, sender ID, media type) is logged at `INFO` level, while sensitive message content is restricted to `DEBUG` level to prevent confidential data exposure in cloud log aggregators.
- **Hardened Docker Container:** Multi-stage/pruned container execution running as an unprivileged non-root user (`appuser`, UID 10001) with built-in container health checks.

---

## 📂 Project Structure

```text
telegram-forwarder/
├── config.py                 # Pydantic v2 settings, environment validation & username normalizer
├── telegram_client.py        # Telethon client wrapper, forwarding engine, FloodWait & fallback logic
├── web_app.py                # FastAPI app with clean lifespan context and health probes (/health, /live)
├── main.py                   # Application entrypoint & Uvicorn runner
├── generate_session.py       # Interactive CLI tool to generate TG_SESSION_STRING locally
├── requirements.txt           # Pinned production and test dependencies
├── Dockerfile                 # Hardened non-root container specification
├── render.yaml               # Render Blueprint infrastructure-as-code definition
├── pytest.ini                # Pytest configuration with strict asyncio loop scopes
├── .env.example              # Template documenting all environment variables
└── tests/
    ├── __init__.py
    ├── test_config.py        # Settings validation and username normalization tests
    ├── test_generate_session.py # Session generator CLI mock tests
    ├── test_telegram.py      # MTProto forwarding, FloodWait, restricted fallback & dedup tests
    └── test_web.py           # Health endpoints, HTTP status codes & lifespan tests
```

---

## 📋 Prerequisites

1. **Python 3.11+** installed locally.
2. A Telegram account.
3. Telegram **API ID** and **API Hash**:
   - Log into [https://my.telegram.org](https://my.telegram.org).
   - Navigate to **API development tools**.
   - Create an application (or use an existing one) to obtain your `api_id` and `api_hash`.

---

## 🚀 Step-by-Step Setup Guide

### Step 1: Clone the Repository

```bash
git clone https://github.com/varunx89/telegram-forwarder.git
cd telegram-forwarder
```

### Step 2: Create and Activate Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Generate Your Telethon Session String

Because cloud hosts (like Render) lack an interactive terminal for entering Telegram SMS/2FA codes, generate your `TG_SESSION_STRING` locally:

```bash
python generate_session.py
```

Follow the interactive terminal prompts:
1. Enter your `API_ID` and `API_HASH`.
2. Enter your phone number with international country code (e.g. `+1234567890`).
3. Enter the verification code sent to your Telegram app.
4. Enter your 2FA Cloud Password (if enabled on your account).

The script outputs a long string starting with `1BVts...`. Copy this value.

### Step 5: Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your configuration:

```ini
TG_API_ID=12345678
TG_API_HASH=your_32_character_api_hash
TG_SESSION_STRING=1BVtsOIWbu0...paste_your_telethon_string_session_here...

# Source group to monitor
TARGET_GROUP_NAME=Premium Membership Group
# Optional numeric ID (takes precedence over title):
# TARGET_GROUP_ID=-1001234567890

# Destination recipient (username, numeric ID, channel ID, or 'me')
FORWARD_TO_USERNAME=@your_recipient_username_or_id

FALLBACK_COPY_ON_RESTRICTED=true
LOG_LEVEL=INFO
PORT=10000
```

### Step 6: Run the Service Locally

```bash
python main.py
```

The service will:
1. Initialize the Telethon client with your session string over IPv6 MTProto.
2. Verify user authorization with Telegram MTProto gateways.
3. Resolve and cache the destination recipient entity.
4. Start listening for new messages in the target group.
5. Bind the FastAPI health check server to `http://[::]:10000` (dual-stack / IPv6-only).

### Step 7: Verify the Health Check

In another terminal window:

```bash
curl -i http://localhost:10000/health
# Or on an IPv6-only VM:
curl -g -i "http://[::1]:10000/health"
```

Expected response when healthy:
```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "running": true,
  "connected": true,
  "ipv6": true
}
```

---

## ⚙️ Configuration Reference Table

| Variable Name | Type | Required | Default | Description |
|:---|:---:|:---:|:---|:---|
| `TG_API_ID` | `int` | **Yes** | `None` | Telegram API ID from https://my.telegram.org |
| `TG_API_HASH` | `str` | **Yes** | `None` | Telegram API Hash from https://my.telegram.org |
| `TG_SESSION_STRING` | `str` | **Yes** | `None` | Base64 Telethon StringSession from `generate_session.py` |
| `TARGET_GROUP_NAME` | `str` | Conditional | `"Premium Membership Group"` | Title of group/channel to monitor (case-insensitive) |
| `TARGET_GROUP_ID` | `int` | Optional | `None` | Exact numeric ID of source chat (e.g. `-1001234567890`). Takes strict precedence over title matching. |
| `FORWARD_TO_USERNAME` | `str` | **Yes** | `""` | Recipient identifier: `@username`, numeric user ID (`123456`), channel ID (`-100123456`), or `'me'` / `'self'`. |
| `FALLBACK_COPY_ON_RESTRICTED` | `bool` | Optional | `true` | When `true`, automatically copies text and media if forwarding is restricted by source chat. |
| `USE_IPV6` | `bool` | Optional | `true` | Enable IPv6 for Telegram MTProto and outbound connections (essential for VMs without outbound IPv4). |
| `TG_USE_IPV6` | `bool` | Optional | `None` | Explicit override specifically for Telegram MTProto connection IPv6 mode. |
| `HOST` | `str` | Optional | `"::"` | Bind address for health check server (`"::"` binds to all IPv6 and IPv4 interfaces; use `"0.0.0.0"` for IPv4-only). |
| `PORT` | `int` | Optional | `10000` | Port for health check server (Render default `$PORT` or `10000`) |
| `LOG_LEVEL` | `str` | Optional | `"INFO"` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 🚢 Cloud Deployment

### Deploying on Render

1. Fork or push your repository to GitHub.
2. In the Render Dashboard, create a **New Web Service** and link your repository, or use the **Blueprints** option selecting `render.yaml`.
3. Set the required Environment Variables in Render:
   - `TG_API_ID`
   - `TG_API_HASH`
   - `TG_SESSION_STRING`
   - `FORWARD_TO_USERNAME`
   - (Optional) `TARGET_GROUP_NAME` or `TARGET_GROUP_ID`
4. Set **Health Check Path** to `/health`.
5. Deploy! Render will build the service and probe `/health`. Once connected, the service starts forwarding automatically.

### Deploying with Docker

Build the hardened Docker image:

```bash
docker build -t telegram-forwarder .
```

Run the container:

```bash
docker run -d \
  --name telegram-forwarder \
  -p 10000:10000 \
  --env-file .env \
  --restart unless-stopped \
  telegram-forwarder
```

Inspect container status and health:

```bash
docker ps
docker logs -f telegram-forwarder
```

---

## 🧪 Automated Testing

The repository includes a comprehensive automated test suite (42 unit and integration tests) with full mocks for Telegram MTProto, Telethon events, media previews, rate limiting, and HTTP health endpoints:

```bash
.venv/bin/pytest -v
```

All 42 tests execute locally with zero external network calls and 100% pass rate.
