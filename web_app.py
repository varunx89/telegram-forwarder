import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from telegram_client import service

logger = logging.getLogger("telegram_forwarder.web")

app = FastAPI(
    title="Telegram Forwarder",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def make_token() -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        settings.ADMIN_PASSWORD.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

EXPECTED_TOKEN = make_token()

def is_authenticated(request: Request) -> bool:
    cookie_val = request.cookies.get(settings.COOKIE_NAME)
    if cookie_val and hmac.compare_digest(cookie_val, EXPECTED_TOKEN):
        return True
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if hmac.compare_digest(token, EXPECTED_TOKEN) or hmac.compare_digest(token, settings.ADMIN_PASSWORD):
            return True
            
    return False

def require_admin(request: Request):
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )
    return True

class SendCodeRequest(BaseModel):
    phone: str

class VerifyCodeRequest(BaseModel):
    code: str

class SubmitPasswordRequest(BaseModel):
    password: str

@app.get("/health")
async def health_check():
    return {"status": "ok", "is_authorized": service.auth_state == "AUTHORIZED"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error}
    )

@app.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    if hmac.compare_digest(password, settings.ADMIN_PASSWORD):
        redirect_resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        redirect_resp.set_cookie(
            key=settings.COOKIE_NAME,
            value=EXPECTED_TOKEN,
            httponly=True,
            samesite="lax",
            secure=False
        )
        return redirect_resp
    else:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid Password"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

@app.get("/logout")
async def logout():
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect_resp.delete_cookie(key=settings.COOKIE_NAME)
    return redirect_resp

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    status_info = await service.get_status()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"status": status_info}
    )

@app.post("/api/auth/send-code", dependencies=[Depends(require_admin)])
async def api_send_code(body: SendCodeRequest):
    return await service.send_code(body.phone)

@app.post("/api/auth/verify-code", dependencies=[Depends(require_admin)])
async def api_verify_code(body: VerifyCodeRequest):
    return await service.verify_code(body.code)

@app.post("/api/auth/submit-password", dependencies=[Depends(require_admin)])
async def api_submit_password(body: SubmitPasswordRequest):
    return await service.submit_password(body.password)

@app.post("/api/auth/logout", dependencies=[Depends(require_admin)])
async def api_logout():
    return await service.logout()
