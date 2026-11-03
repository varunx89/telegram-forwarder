# Telegram Forwarder Service

A secure, containerized Python service built with **Telethon** and **FastAPI** that monitors a specific Telegram group (**"Premium Membership Group"**) and forwards incoming messages directly to **@V_C_0_3**.

Includes a web-based administration panel and 3-step browser authentication wizard (Phone → Code → 2FA Cloud Password) designed specifically for cloud environments like **Render** where interactive shell access is unavailable.

---

## ✨ Key Features

- **Zero-Local Login (Strictly Cloud-Bound):** No local terminal login needed. The service boots in an unauthenticated state, exposes a secure browser login UI, and guides you through logging in directly on Render.
- **Zero-Downtime Session Persistence:** Once authenticated, the dashboard exports an encrypted `TG_SESSION_STRING` (Telethon StringSession). Setting this in Render's environment variables keeps your session alive permanently across restarts without requiring persistent disks.
- **Exact Group Filtering & Target Matching:** Filters messages strictly by group name (`Premium Membership Group`) or optional exact numeric ID (`TARGET_GROUP_ID`).
- **Target Forwarding to @V_C_0_3:** Automatically resolves the target entity handle and delivers exact Telegram forwards with original sender attributes.
- **Restricted Content Fallback:** Automatically detects if the source group has "Restrict saving content" (`ChatForwardsRestrictedError`) enabled and falls back to copying text, formatted entities, and media directly.
- **Message Deduplication:** In-memory LRU deduplication window ensures duplicated network events do not cause duplicate forwards.
- **Hardened Admin UI:**
  - Constant-time password verification (`hmac.compare_digest`) against timing attacks.
  - Signed, `HttpOnly`, `SameSite=Lax` authentication session cookies.
  - Sensitive data masking (phone numbers masked as `+12****89`).
- **Render-Ready:** Includes `render.yaml` Blueprint, Dockerfile, and `/health` probe.

---

## 📂 Project Structure

```text
telegram-forwarder/
├── config.py            # Pydantic v2 settings, environment validation & username normalizer
├── telegram_client.py   # Telethon client wrapper, auth state machine & forwarding engine
├── web_app.py           # FastAPI web service, cookie auth & protected login API
├── main.py              # Application lifespan & Uvicorn runner
├── requirements.txt      # Pinned production and test dependencies
├── Dockerfile            # Container definition (Python 3.11-slim)
├── render.yaml          # Render Blueprint deployment definition
├── .env.example         # Template for environment variables
├── static/
│   ├── style.css        # Responsive dashboard styling
│   └── app.js          # Browser login wizard & live log polling
├── templates/
│   ├── base.html         # Jinja2 layout
│   ├── login.html        # Secure admin password login page
│   └── dashboard.html    # Status panel, login wizard & live activity audit
└── tests/
    ├── test_config.py      # Configuration tests
    ├── test_telegram.py    # Group filtering, forwarding & deduplication tests
    ├── test_auth_flow.py   # State machine, SMS code & 2FA mock tests
    └── test_web.py         # HTTP endpoints & security tests
```

---

## 🔐 Security Considerations

1. **Admin Dashboard Authentication:** The web UI is protected by `ADMIN_PASSWORD`. Without it, unauthorized visitors cannot trigger code requests or view forwarding logs.
2. **No Telegram Secrets in Logs:** Phone numbers are strictly masked (`+91****21`), and auth tokens are never written into stdout or unencrypted logs.
3. **Render Environment Variables:** Telegram API ID, API Hash, Admin Password, and Session Strings are stored exclusively via Render Environment Variables, keeping them out of source control.

---

## 🧪 Running Tests Locally

To run the 24 automated unit tests:

```bash
cd /home/server/Programming/telegram-forwarder
.venv/bin/pytest -v
```
