import os
import json
import base64
import datetime
from pathlib import Path
from typing import Optional, List
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Dizin Yapılandırması
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"

CLICKSEND_API_BASE = "https://rest.clicksend.com/v3"
SMS_SEND_ENDPOINT = f"{CLICKSEND_API_BASE}/sms/send"
ACCOUNT_ENDPOINT = f"{CLICKSEND_API_BASE}/account"

app = FastAPI(title="ClickSend SMS Panel", version="1.0.0")


# --- Modeller ---
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


# --- Yardımcı Fonksiyonlar ---
def get_stored_settings() -> dict:
    settings = {
        "username": os.getenv("CLICKSEND_USERNAME", ""),
        "api_key": os.getenv("CLICKSEND_API_KEY", ""),
        "default_domain": os.getenv("DEFAULT_DOMAIN", ""),
        "default_sender_id": os.getenv("DEFAULT_SENDER_ID", "")
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings.update(saved)
        except Exception:
            pass
    return settings


def save_stored_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


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
    history = history[:100]  # En son 100 kaydı sakla
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def execute_clicksend_sms(to_number: str, message_body: str, sender_id: Optional[str] = None):
    settings = get_stored_settings()
    username = settings.get("username")
    api_key = settings.get("api_key")

    if not username or not api_key:
        raise ValueError("ClickSend kullanıcı adı ve API anahtarı ayarlanmamış. Lütfen Ayarlar sekmesinden girin.")

    payload = {
        "messages": [
            {
                "to": to_number,
                "body": message_body,
                "source": "dokploy-web-panel"
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


# --- API Endpointleri ---
@app.get("/api/settings")
def get_settings():
    settings = get_stored_settings()
    has_api_key = bool(settings.get("api_key"))
    return {
        "username": settings.get("username", ""),
        "has_api_key": has_api_key,
        "default_domain": settings.get("default_domain", ""),
        "default_sender_id": settings.get("default_sender_id", "")
    }


@app.post("/api/settings")
def save_settings(payload: SettingsPayload):
    current = get_stored_settings()
    current["username"] = payload.username
    if payload.api_key:
        current["api_key"] = payload.api_key
    if payload.default_domain is not None:
        current["default_domain"] = payload.default_domain
    if payload.default_sender_id is not None:
        current["default_sender_id"] = payload.default_sender_id

    save_stored_settings(current)
    return {"success": True, "message": "Ayarlar başarıyla kaydedildi."}


@app.get("/api/balance")
def get_balance():
    settings = get_stored_settings()
    username = settings.get("username")
    api_key = settings.get("api_key")

    if not username or not api_key:
        return {
            "success": False,
            "error": "ClickSend Kullanıcı Adı ve API Key henüz yapılandırılmamış."
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
def api_send_sms(payload: SendSmsPayload):
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
def api_send_verification(payload: SendVerificationPayload):
    domain = payload.domain.replace("https://", "").replace("http://", "").strip("/")
    if payload.token:
        link = f"https://{domain}/verify?token={payload.token}"
        body = f"Kayıt doğrulama linkiniz: {link}"
    elif payload.code:
        body = f"Kayıt doğrulama kodunuz: {payload.code}. https://{domain}"
    else:
        body = f"Kaydınız başarıyla tamamlandı: https://{domain}"

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
def get_history():
    return load_history()


@app.delete("/api/history")
def clear_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    return {"success": True, "message": "Geçmiş temizlendi."}


# Statik Dosyalar ve Anasayfa
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"status": "running", "message": "ClickSend SMS API Panel"})
