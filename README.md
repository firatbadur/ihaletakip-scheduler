# ihaletakip-scheduler

IhaleTakip mobil uygulaması için Python bildirim servisi. Kullanıcıların takip ettikleri ihalelerin (alarms) durumunu ve kayıtlı filtrelerine uyan yeni ihaleleri günlük olarak EKAP'tan çeker; eşleşmeleri FCM push + Firestore notification olarak kullanıcıya iletir.

## Özellikler

- **AlarmJob** (her gün 09:00 TR): alarms koleksiyonundaki ihalelerin doküman değişikliği / ihale günü / tamamlanma tespiti
- **SavedFilterJob** (her gün 10:00 TR): bugün yayınlanmış + filtrelere uyan yeni ihalelerin bildirimi
- EKAP v2 AES-192-CBC imzalama (mobil crypto-js ile parity)
- Token-bucket rate limiter + eş zamanlılık semaforu + jitter + 429/5xx retry
- Redis tabanlı state & idempotency
- Firestore dual-write (FCM push + `users/{uid}/notifications`)
- Loguru ile PII redaction, dosya rotasyonu
- Docker Compose + Redis deployment

## Gereksinimler

- Python 3.11+
- Redis 7+
- Firebase service account JSON (mobil projeden: `IhaleTakip/scripts/serviceAccountKey.json`)

## Hızlı Başlangıç (Lokal)

```bash
# Bağımlılıklar
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# Konfig
cp .env.example .env
# .env'i düzenle — özellikle FIREBASE_CREDENTIALS_PATH ve REDIS_URL

# Service account dosyasını kopyala
cp /path/to/serviceAccountKey.json scripts/

# Testler
.venv/bin/pytest

# Manuel dry-run
.venv/bin/python scripts/run_once.py alarm --dry-run
.venv/bin/python scripts/run_once.py saved_filter --dry-run

# Servisi başlat (Redis çalışır olmalı)
.venv/bin/python -m app.main
```

## Docker Compose (Deploy)

```bash
cp .env.example .env    # düzenle
cp /path/to/serviceAccountKey.json scripts/
docker compose build
docker compose up -d
docker compose logs -f scheduler
```

Tüm state kalıcı volume'larda (`redis_data`, `scheduler_logs`).

## Proje Yapısı

```
app/
├── main.py                 # Entrypoint
├── config.py               # pydantic-settings
├── firebase/               # Firebase Admin SDK, Firestore repo, FCM sender
├── ekap/                   # EKAP v2 client, crypto (signing), models
├── http/                   # rate limiter, retry, session
├── jobs/                   # AlarmJob + SavedFilterJob (+ BaseJob)
├── scheduler/              # AsyncIOScheduler wiring
├── notifications/          # Dispatcher (dual-write) + templates
├── state/                  # StateStore protocol + Redis impl
├── dedup/                  # Grouper: alarms-by-tender, filters-by-fingerprint
└── utils/                  # logging, dates, errors, metrics

scripts/
├── run_once.py                 # CLI: manuel tek job trigger
├── node_crypto_reference.js    # EKAP signing parity referansı (Node + crypto-js)
└── serviceAccountKey.json      # GIT-IGNORED

tests/                      # pytest + fakeredis
```

## Ayarlar (ortam değişkenleri)

Tümü `.env` veya container environment üzerinden okunur. `.env.example` detay içerir.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `FIREBASE_PROJECT_ID` | `ihale-53fbf` | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | `/secrets/serviceAccountKey.json` | Service account JSON |
| `EKAP_BASE_URL` | `https://ekapv2.kik.gov.tr` | EKAP v2 base URL |
| `EKAP_SIGNING_KEY` | `Qm2LtXR0aByP69vZNKef4wMJ` | AES-192 imza anahtarı |
| `EKAP_RATE_PER_MIN` | `30` | Token bucket hızı |
| `EKAP_CONCURRENCY` | `3` | Eş zamanlı istek limiti |
| `ALARM_CRON` | `0 9 * * *` | AlarmJob cron (TR) |
| `SAVED_FILTER_CRON` | `0 10 * * *` | SavedFilterJob cron (TR) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis bağlantısı |
| `TIMEZONE` | `Europe/Istanbul` | Cron + tarih timezone'u |
| `DRY_RUN` | `false` | FCM'yi bypass et (Firestore yazmaları yine yapılır) |
| `ONLY_BETA_USERS` | `false` | Sadece `isBeta=true` kullanıcılara gönder |
| `LOG_LEVEL` | `INFO` | Loguru seviyesi |

## Lisans

Proprietary — internal use only.
