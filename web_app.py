import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from telegram_client import service

logger = logging.getLogger("telegram_forwarder.web")

app = FastAPI(
    title="Telegram Forwarder Service",
    description="Secure Telethon forwarding service with browser-based authentication.",
    version="1.0.0"
)

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def make_token() -> str:
    """Generate a cryptographic authentication token derived from ADMIN_PASSWORD and SECRET_KEY."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        settings.ADMIN_PASSWORD.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

EXPECTED_TOKEN = make_token()

def is_authenticated(request: Request) -> bool:
    """Verify session cookie or Authorization header."""
    cookie_val = request.cookies.get(settings.COOKIE_NAME)
    if cookie_val and hmac.compare_digest(cookie_val, EXPECTED_TOKEN):
        return True
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        # Accept either the generated token or the direct ADMIN_PASSWORD
        if hmac.compare_digest(token, EXPECTED_TOKEN) or hmac.compare_digest(token, settings.ADMIN_PASSWORD):
            return True
            
    return False

def require_admin(request: Request):
    """Dependency to protect API endpoints."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Invalid or missing admin credentials."
        )
    return True

# Pydantic request models
class SendCodeRequest(BaseModel):
    phone: str

class VerifyCodeRequest(BaseModel):
    code: str

class SubmitPasswordRequest(BaseModel):
    password: str

# Health Check (Public, for Render)
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "service": "telegram-forwarder",
        "auth_state": service.auth_state,
        "is_authorized": service.auth_state == "AUTHORIZED"
    }

# Login Page & Form
@app.get("/login", response_class=HTMLResponse, tags=["Auth UI"])
async def login_page(request: Request, error: Optional[str] = None):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error}
    )

@app.post("/login", tags=["Auth UI"])
async def login_post(request: Request, response: Response, password: str = Form(...)):
    # Constant-time comparison to prevent timing attacks
    if hmac.compare_digest(password, settings.ADMIN_PASSWORD):
        redirect_resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        redirect_resp.set_cookie(
            key=settings.COOKIE_NAME,
            value=EXPECTED_TOKEN,
            httponly=True,
            samesite="lax",
            secure=False  # Handled over HTTPS on Render
        )
        return redirect_resp
    else:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid Admin Password. Please try again."},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

@app.get("/logout", tags=["Auth UI"])
async def logout(response: Response):
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect_resp.delete_cookie(key=settings.COOKIE_NAME)
    return redirect_resp

# Main Dashboard (Protected)
@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    status_info = await service.get_status()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "status": status_info,
            "settings": settings,
            "logs": list(service.activity_logs)
        }
    )

# Protected JSON API Endpoints for the browser login wizard
@app.get("/api/status", dependencies=[Depends(require_admin)], tags=["API"])
async def api_status():
    return await service.get_status()

@app.get("/api/logs", dependencies=[Depends(require_admin)], tags=["API"])
async def api_logs():
    return {"logs": list(service.activity_logs)}

@app.post("/api/auth/send-code", dependencies=[Depends(require_admin)], tags=["API"])
async def api_send_code(body: SendCodeRequest):
    return await service.send_code(body.phone)

@app.post("/api/auth/verify-code", dependencies=[Depends(require_admin)], tags=["API"])
async def api_verify_code(body: VerifyCodeRequest):
    return await service.verify_code(body.code)

@app.post("/api/auth/submit-password", dependencies=[Depends(require_admin)], tags=["API"])
async def api_submit_password(body: SubmitPasswordRequest):
    return await service.submit_password(body.password)

@app.post("/api/auth/logout", dependencies=[Depends(require_admin)], tags=["API"])
async def api_logout():
    return await service.logout()
