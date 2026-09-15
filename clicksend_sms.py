import os
import sys
import json
import base64
import argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ClickSend REST API v3 Endpoints
CLICKSEND_API_BASE = "https://rest.clicksend.com/v3"
SMS_SEND_ENDPOINT = f"{CLICKSEND_API_BASE}/sms/send"
ACCOUNT_ENDPOINT = f"{CLICKSEND_API_BASE}/account"


def load_env_file(filepath: str = ".env") -> None:
    """Basit .env dosyası okuyucu (harici kütüphane gerektirmez)."""
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val


# Script başlatıldığında .env dosyasını otomatik yükle
load_env_file()


def get_auth_header(username: str, api_key: str) -> str:
    """ClickSend HTTP Basic Auth başlığı üretir."""
    credentials = f"{username}:{api_key}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def check_balance(username: str = None, api_key: str = None) -> dict:
    """
    ClickSend hesap bakiyesini ve kimlik bilgilerinin doğruluğunu kontrol eder.
    """
    username = username or os.getenv("CLICKSEND_USERNAME")
    api_key = api_key or os.getenv("CLICKSEND_API_KEY")

    if not username or not api_key:
        raise ValueError("CLICKSEND_USERNAME ve CLICKSEND_API_KEY tanımlanmalıdır.")

    req = Request(
        ACCOUNT_ENDPOINT,
        headers={
            "Authorization": get_auth_header(username, api_key),
            "Content-Type": "application/json"
        }
    )

    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "success": True,
                "balance": data.get("data", {}).get("balance"),
                "currency": data.get("data", {}).get("currency"),
                "email": data.get("data", {}).get("user_email"),
                "raw": data
            }
    except HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {"success": False, "status_code": e.code, "error": err_body}
    except URLError as e:
        return {"success": False, "error": str(e.reason)}


def send_sms(
    to_number: str,
    message_body: str,
    sender_id: str = None,
    username: str = None,
    api_key: str = None
) -> dict:
    """
    ClickSend API üzerinden SMS gönderir.
    
    :param to_number: Alıcı telefon numarası (E.164 formatında, örn: +90532xxxxxxx)
    :param message_body: SMS içeriği
    :param sender_id: Gönderici başlığı/numarası (opsiyonel)
    :param username: ClickSend kullanıcı adı (varsayılan: os.getenv)
    :param api_key: ClickSend API Key (varsayılan: os.getenv)
    """
    username = username or os.getenv("CLICKSEND_USERNAME")
    api_key = api_key or os.getenv("CLICKSEND_API_KEY")

    if not username or not api_key:
        raise ValueError("CLICKSEND_USERNAME ve CLICKSEND_API_KEY tanımlanmalıdır.")

    payload = {
        "messages": [
            {
                "to": to_number,
                "body": message_body,
                "source": "website-registration-script"
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

    try:
        with urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            result = json.loads(resp_body)
            return {
                "success": True,
                "http_code": resp.status,
                "response_code": result.get("response_code"),
                "response_msg": result.get("response_msg"),
                "data": result.get("data")
            }
    except HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = err_body
        return {
            "success": False,
            "http_code": e.code,
            "error": err_json
        }
    except URLError as e:
        return {
            "success": False,
            "error": str(e.reason)
        }


def send_registration_verification(
    to_number: str,
    site_domain: str,
    code: str = None,
    verify_token: str = None
) -> dict:
    """
    Web sitesi kaydı (Website Registration) için doğrulama SMS'i gönderir.
    
    NOT: Dashboard'da (https://dashboard.clicksend.com/sms/website-registration)
    onaylatılmış olan domain/linki içerir.
    """
    clean_domain = site_domain.replace("https://", "").replace("http://", "").strip("/")
    if verify_token:
        link = f"https://{clean_domain}/verify?token={verify_token}"
        body = f"Kayıt doğrulama linkiniz: {link}"
    elif code:
        body = f"Kayıt doğrulama kodunuz: {code}. https://{clean_domain}"
    else:
        body = f"Kaydınız başarıyla tamamlandı. Giriş için: https://{clean_domain}"

    return send_sms(to_number=to_number, message_body=body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClickSend SMS Entegrasyon Aracı")
    parser.add_argument("--to", help="Alıcı telefon numarası (+905xxxxxxxxx)")
    parser.add_argument("--message", help="Gönderilecek SMS metni")
    parser.add_argument("--check-balance", action="store_true", help="Hesap bakiyesini sorgular")
    parser.add_argument("--domain", help="ClickSend üzerinde kayıtlı domain adı (örn: siteniz.com)")
    parser.add_argument("--code", help="Doğrulama kodu (örn: 123456)")

    args = parser.parse_args()

    if args.check_balance:
        print("ClickSend hesap bilgileri sorgulanıyor...")
        try:
            res = check_balance()
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Hata: {e}")
            sys.exit(1)
        sys.exit(0)

    if args.to:
        try:
            if args.domain and args.code:
                print(f"Kayıt doğrulama SMS'i gönderiliyor: {args.to} ...")
                res = send_registration_verification(
                    to_number=args.to,
                    site_domain=args.domain,
                    code=args.code
                )
            else:
                msg = args.message or "ClickSend entegrasyon test mesajıdır."
                print(f"SMS gönderiliyor: {args.to} ...")
                res = send_sms(to_number=args.to, message_body=msg)
                
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Hata: {e}")
            sys.exit(1)
    else:
        print("=" * 60)
        print("ClickSend SMS Entegrasyon Scripti")
        print("=" * 60)
        print("Kullanım Örnekleri:")
        print("  1. Hesap bakiyesi kontrolü:")
        print("     python clicksend_sms.py --check-balance")
        print("\n  2. Test SMS gönderme:")
        print('     python clicksend_sms.py --to "+905xxxxxxxxx" --message "Merhaba, bu bir test mesajıdır."')
        print("\n  3. Web sitesi kayıt doğrulama SMS'i:")
        print('     python clicksend_sms.py --to "+905xxxxxxxxx" --domain "siteniz.com" --code "482910"')
        print("=" * 60)
