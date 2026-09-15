import os
import json
import base64
import secrets
import datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Dizin Yapılandırması
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Otomatik .env yükleyici
def load_env_file(filepath = BASE_DIR / ".env"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

load_env_file()

SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"

CLICKSEND_API_BASE = "https://rest.clicksend.com/v3"
SMS_SEND_ENDPOINT = f"{CLICKSEND_API_BASE}/sms/send"
ACCOUNT_ENDPOINT = f"{CLICKSEND_API_BASE}/account"

app = FastAPI(title="Operations Console", version="1.0.0", docs_url=None, redoc_url=None)


# --- Modeller ---
class LoginPayload(BaseModel):
    username: str
    password: str


class ChangePasswordPayload(BaseModel):
    old_password: str
    new_username: Optional[str] = None
    new_password: str


class SettingsPayload(BaseModel):
    username: str
    api_key: Optional[str] = None
    default_domain: Optional[str] = "siteniz.com"
    default_sender_id: Optional[str] = ""


class SendSmsPayload(BaseModel):
    to: str
    message: str
    sender_id: Optional[str] = None


class SendVerificationPayload(BaseModel):
    to: str
    domain: str
    code: Optional[str] = None
    token: Optional[str] = None


# --- Ayarlar & Oturum Yönetimi ---
def get_stored_settings() -> dict:
    settings = {
        "admin_username": (os.getenv("ADMIN_USERNAME") or "admin").strip(),
        "admin_password": (os.getenv("ADMIN_PASSWORD") or "admin123").strip(),
        "username": (os.getenv("CLICKSEND_USERNAME") or "").strip(),
        "api_key": (os.getenv("CLICKSEND_API_KEY") or "").strip(),
        "default_domain": (os.getenv("DEFAULT_DOMAIN") or "").strip(),
        "default_sender_id": (os.getenv("DEFAULT_SENDER_ID") or "").strip()
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    # Dosyadaki değer boş değilse kullan
                    if v is not None and str(v).strip() != "":
                        settings[k] = str(v).strip()
        except Exception:
            pass
    return settings


def save_stored_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_sessions(sessions: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f)


def create_session(username: str) -> str:
    token = secrets.token_hex(32)
    sessions = load_sessions()
    # 30 gün geçerli oturum
    expires = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
    sessions[token] = {"username": username, "expires": expires}
    save_sessions(sessions)
    return token


def verify_session(token: Optional[str]) -> bool:
    if not token:
        return False
    sessions = load_sessions()
    sess = sessions.get(token)
    if not sess:
        return False
    try:
        exp = datetime.datetime.fromisoformat(sess.get("expires", ""))
        if datetime.datetime.now() > exp:
            del sessions[token]
            save_sessions(sessions)
            return False
    except Exception:
        return False
    return True


def remove_session(token: Optional[str]):
    if not token:
        return
    sessions = load_sessions()
    if token in sessions:
        del sessions[token]
        save_sessions(sessions)


def require_auth(req: FastAPIRequest):
    # Çerezden veya Header'dan token al
    token = req.cookies.get("portal_session")
    if not token:
        auth_header = req.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not verify_session(token):
        raise HTTPException(status_code=401, detail="Oturum süresi dolmuş veya geçersiz.")
    return True


def get_auth_header(username: str, api_key: str) -> str:
    creds = f"{username}:{api_key}"
    encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def record_history(item: dict):
    history = load_history()
    history.insert(0, item)
    history = history[:100]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def execute_clicksend_sms(to_number: str, message_body: str, sender_id: Optional[str] = None):
    settings = get_stored_settings()
    username = settings.get("username")
    api_key = settings.get("api_key")

    if not username or not api_key:
        raise ValueError("API kimlik bilgileri eksik. Lütfen Ayarlar sekmesinden yapılandırın.")

    payload = {
        "messages": [
            {
                "to": to_number,
                "body": message_body,
                "source": "dokploy-portal"
            }
        ]
    }
    if sender_id:
        payload["messages"][0]["from"] = sender_id

    data_bytes = json.dumps(payload).encode("utf-8")
    req = Request(
        SMS_SEND_ENDPOINT,
        data=data_bytes,
        headers={
            "Authorization": get_auth_header(username, api_key),
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )

    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            result = json.loads(resp_body)
            history_entry = {
                "timestamp": now_iso,
                "to": to_number,
                "message": message_body,
                "status": "SUCCESS",
                "http_code": resp.status,
                "response_msg": result.get("response_msg")
            }
            record_history(history_entry)
            return {
                "success": True,
                "http_code": resp.status,
                "response_msg": result.get("response_msg"),
                "data": result.get("data")
            }
    except HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = err_body
        history_entry = {
            "timestamp": now_iso,
            "to": to_number,
            "message": message_body,
            "status": "ERROR",
            "http_code": e.code,
            "response_msg": str(err_json)
        }
        record_history(history_entry)
        return {
            "success": False,
            "http_code": e.code,
            "error": err_json
        }
    except URLError as e:
        history_entry = {
            "timestamp": now_iso,
            "to": to_number,
            "message": message_body,
            "status": "ERROR",
            "http_code": 0,
            "response_msg": str(e.reason)
        }
        record_history(history_entry)
        return {
            "success": False,
            "error": str(e.reason)
        }


# --- Kimlik Doğrulama Endpointleri ---
@app.post("/api/login")
def api_login(payload: LoginPayload, response: Response):
    settings = get_stored_settings()
    expected_user = settings.get("admin_username", "admin")
    expected_pass = settings.get("admin_password", "admin123")

    if payload.username == expected_user and payload.password == expected_pass:
        token = create_session(payload.username)
        response.set_cookie(
            key="portal_session",
            value=token,
            max_age=30 * 24 * 3600,
            httponly=False,
            samesite="lax"
        )
        return {"success": True, "token": token, "username": payload.username}
    raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")


@app.post("/api/logout")
def api_logout(req: FastAPIRequest, response: Response):
    token = req.cookies.get("portal_session")
    if token:
        remove_session(token)
    response.delete_cookie(key="portal_session")
    return {"success": True, "message": "Çıkış yapıldı."}


@app.get("/api/auth/status")
def auth_status(req: FastAPIRequest):
    token = req.cookies.get("portal_session")
    if not token:
        auth_header = req.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    is_valid = verify_session(token)
    return {"authenticated": is_valid}


@app.post("/api/change-admin-auth")
def change_admin_auth(payload: ChangePasswordPayload, auth: bool = Depends(require_auth)):
    settings = get_stored_settings()
    if payload.old_password != settings.get("admin_password"):
        raise HTTPException(status_code=400, detail="Mevcut şifre hatalı.")

    if payload.new_username:
        settings["admin_username"] = payload.new_username.strip()
    if payload.new_password:
        settings["admin_password"] = payload.new_password.strip()

    save_stored_settings(settings)
    return {"success": True, "message": "Giriş bilgileri başarıyla güncellendi."}


# --- Korumalı Uygulama Endpointleri ---
@app.get("/api/settings")
def get_settings(auth: bool = Depends(require_auth)):
    settings = get_stored_settings()
    has_api_key = bool(settings.get("api_key"))
    return {
        "username": settings.get("username", ""),
        "has_api_key": has_api_key,
        "default_domain": settings.get("default_domain", ""),
        "default_sender_id": settings.get("default_sender_id", ""),
        "admin_username": settings.get("admin_username", "admin")
    }


@app.post("/api/settings")
def save_settings(payload: SettingsPayload, auth: bool = Depends(require_auth)):
    current = get_stored_settings()
    current["username"] = payload.username
    if payload.api_key:
        current["api_key"] = payload.api_key
    if payload.default_domain is not None:
        current["default_domain"] = payload.default_domain
    if payload.default_sender_id is not None:
        current["default_sender_id"] = payload.default_sender_id

    save_stored_settings(current)
    return {"success": True, "message": "Ayarlar kaydedildi."}


@app.get("/api/balance")
def get_balance(auth: bool = Depends(require_auth)):
    settings = get_stored_settings()
    username = settings.get("username")
    api_key = settings.get("api_key")

    if not username or not api_key:
        return {
            "success": False,
            "error": "API kimlik bilgileri yapılandırılmamış."
        }

    req = Request(
        ACCOUNT_ENDPOINT,
        headers={
            "Authorization": get_auth_header(username, api_key),
            "Content-Type": "application/json"
        }
    )

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            account_data = data.get("data", {})
            return {
                "success": True,
                "balance": account_data.get("balance"),
                "currency": account_data.get("currency"),
                "email": account_data.get("user_email")
            }
    except HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {"success": False, "status_code": e.code, "error": err_body}
    except URLError as e:
        return {"success": False, "error": str(e.reason)}


@app.post("/api/send-sms")
def api_send_sms(payload: SendSmsPayload, auth: bool = Depends(require_auth)):
    try:
        res = execute_clicksend_sms(
            to_number=payload.to,
            message_body=payload.message,
            sender_id=payload.sender_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send-verification")
def api_send_verification(payload: SendVerificationPayload, auth: bool = Depends(require_auth)):
    domain = payload.domain.replace("https://", "").replace("http://", "").strip("/")
    if payload.token:
        link = f"https://{domain}/verify?token={payload.token}"
        body = f"Doğrulama linkiniz: {link}"
    elif payload.code:
        body = f"Doğrulama kodunuz: {payload.code}. https://{domain}"
    else:
        body = f"İşlem başarıyla tamamlandı: https://{domain}"

    settings = get_stored_settings()
    sender_id = settings.get("default_sender_id") or None

    try:
        res = execute_clicksend_sms(
            to_number=payload.to,
            message_body=body,
            sender_id=sender_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
def get_history(auth: bool = Depends(require_auth)):
    return load_history()


@app.delete("/api/history")
def clear_history(auth: bool = Depends(require_auth)):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    return {"success": True, "message": "Kayıtlar temizlendi."}


# Statik Dosyalar ve Anasayfa
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"status": "running", "message": "Portal Console"})
