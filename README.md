# ClickSend SMS & Website Registration Web Paneli

Dokploy ve Docker uyumlu, ClickSend SMS ve Web Sitesi Kayıt / OTP Doğrulama yönetim paneli.

---

## Özellikler

- **Tarayıcı Üzerinden API Yönetimi**: ClickSend kullanıcı adı, API Key ve varsayılan domain/gönderici başlığını kod düzenlemeden arayüzden ayarlama ve test etme.
- **Website Registration & OTP Entegrasyonu**: [ClickSend Website Registration](https://dashboard.clicksend.com/sms/website-registration) ile onaylattığınız alan adları için tek tıkla OTP / aktivasyon linkli SMS oluşturma ve gönderme.
- **Hızlı SMS Gönderimi**: Karakter ve parça sayacı ile anlık SMS gönderimi.
- **Canlı Bakiye Sorgulama**: ClickSend hesap bakiyesini ve para birimini otomatik/manuel sorgulama.
- **Kalıcı Veri (Volume)**: Arayüzden girilen ayarlar ve loglar `/app/data` altında saklanır, container yeniden başlasa bile silinmez.
- **Dokploy & Docker Uyumlu**: Tek tıkla Dokploy'a deploy edilebilir.

---

## Dokploy ile Dağıtım (Deploy)

Dokploy panelinizde 2 farklı yöntemle kolayca çalıştırabilirsiniz:

### Yöntem 1: Git Repository Olarak (Tavsiye Edilen)
1. Dokploy paneline girin -> **Applications** -> **Create Application**.
2. GitHub veya Git sağlayıcınızı seçip bu depoyu bağlayın.
3. **Build Type**: `Dockerfile` seçin.
4. **Port**: `8000` yazın.
5. **Volumes** (Kalıcı Ayarlar İçin):
   - Host / Volume: `clicksend_data` (veya sunucuda bir dizin örn: `/var/data/clicksend`)
   - Container Path: `/app/data`
6. **Deploy** butonuna tıklayın!

### Yöntem 2: Compose Olarak
1. Dokploy paneline girin -> **Compose** -> **Create Compose**.
2. Depodaki `docker-compose.yml` içeriğini yapıştırın veya repoyu bağlayın.
3. **Deploy** butonuna tıklayın.

---

## Yerel Docker ile Çalıştırma

```bash
# Container'ı arka planda başlatın:
docker compose up -d

# Tarayıcınızda açın:
# http://localhost:8000
```

---

## Yerel Python Ortamında Çalıştırma (Docker Olmadan)

```bash
# Bağımlılıkları yükleyin:
pip install -r requirements.txt

# Uygulamayı başlatın:
uvicorn main:app --reload --port 8000
```

Tarayıcınızdan `http://localhost:8000` adresine giderek **API Ayarları** sekmesinden bilgilerinizi girebilirsiniz.
