FROM python:3.11-slim

# Sistem bağımlılıkları ve çalışma dizini
WORKDIR /app

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Kalıcı veri dizini (Dokploy / Docker volume için)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

# Dokploy için port
EXPOSE 8000

# Uygulamayı başlat
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
