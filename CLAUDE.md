# ihaletakip-scheduler — Claude Code Rehberi

## Proje Amacı

Bu repo, IhaleTakip React Native mobil uygulaması için Ubuntu üzerinde 7/24 çalışan bir Python bildirim servisidir. Mobil uygulama `/Users/tinyfect/Desktop/IhaleTakip/` dizinindedir; bu servis onun Firebase projesi (`ihale-53fbf`) üzerinden kullanıcı verilerini okur ve bildirim üretir.

Üç scheduler job'ı:

1. **AlarmJob** — her gün saat 09:00 TR.
   `users/{uid}/alarms/*` koleksiyonundaki her ihalenin EKAP'tan güncel detayını çeker, önceki state ile karşılaştırır ve:
   - `reminderDay` → ihale günü bildirimi
   - `documentChange` → doküman sayısı değiştiyse bildirim
   - `completed` → sonuçlandıysa bir kerelik bildirim + Firestore'da `alarm.completed=true`
2. **SavedFilterJob** — her gün saat 10:00 TR.
   `users/{uid}/savedFilters/{filterId}` koleksiyonunda `alarm=true` olan tüm filtreleri fingerprint'e göre grupla, **her grup için tek EKAP çağrısı** ile bugün yayınlanmış ihaleleri çek, daha önce bildirilmemiş olanları her kullanıcıya dispatch et.
3. **InterestJob** — her gün 08:00-17:00 arası saat başı (10 tetikleme).
   Kullanıcının kaydettiği filtreleri (alarm flag ayrımı yok) union'layıp EKAP'ta `ihaleDurumIdList=[2,3]` (katılıma açık) ile arama yapar. `alarms` veya `savedTenders`'da **zaten kayıtlı olmayan** + daha önce bu user'a önerilmemiş adaylardan **1 tanesini** "İlgilenebileceğiniz İlan" olarak gönderir. Günde kullanıcı başına max `interest_daily_cap` (varsayılan: 3) bildirim; IKN dedup `interest_dedup_days` gün (varsayılan: 7).

**Kullanıcı filtresi**: Sadece `isPro=true` kullanıcılar bildirim alır (üç job için de geçerli). `isActive != false` + `fcmToken != null` de şarttır.

**Not**: `ilan.gov.tr` bu fazın kapsamı dışıdır — bu repo içinde hiçbir ilan.gov.tr kodu yoktur.

## Komutlar

```bash
# Geliştirme
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# Testler
.venv/bin/pytest                             # tüm testler
.venv/bin/pytest tests/test_ekap_crypto.py   # crypto parity
.venv/bin/ruff check app tests               # lint
.venv/bin/mypy app                           # tip kontrolü

# Manuel tek seferlik job
.venv/bin/python scripts/run_once.py alarm --dry-run
.venv/bin/python scripts/run_once.py saved_filter --dry-run

# Servis (lokal, Redis'e ihtiyaç duyar)
.venv/bin/python -m app.main

# Docker Compose
docker compose build
docker compose up -d
docker compose logs -f scheduler
docker compose down
```

## Mimari Kuralları

- **Async-first**: tüm IO async; Firestore sync SDK'sı `asyncio.to_thread` ile sarılır.
- **EKAP çağrıları asla rate limiter olmadan yapılmaz**. Her request: token bucket → semaphore → jitter → imzalı header → tenacity retry.
- **Dedup önce**: hiç bir zaman aynı tender veya aynı filtre için birden fazla EKAP çağrısı yapılmaz (grouper katmanı).
- **Dual-write dispatcher**: her bildirim hem Firestore'a (`users/{uid}/notifications`) hem FCM'ye yazılır. İdempotency anahtarı Redis'te 7 gün tutulur.
- **Timezone**: her yerde `Europe/Istanbul`. Cron'lar TR saatine göre.
- **Loguru**: `print` yasak, hassas alanlar otomatik redakte edilir (fcmToken, email, private_key).
- **Sync'e kaçma**: `time.sleep`, `requests` kullanma; `asyncio.sleep`, `httpx` kullan.

## Firestore Şeması (mobil projeden)

```
users/{uid}
  email, displayName, photoURL, createdAt, fcmToken, isActive, isBeta, isPro
  alarms/{tenderId | ikn}         ← key: mobil tarafta gecis halinde (tenderIkn alani her zaman var)
    { tenderId, tenderTitle, tenderIkn, institution,
      reminderDay, documentChange, completed }
  savedFilters/{filterId}
    { name, filters, tags, alarm, createdAt }
  savedTenders/{ikn}              ← key = IKN
    { ikn, tenderTitle, ... , savedAt }
  notifications/{notifId}
    { type, title, body, tenderId, tenderTitle, tenderIkn,
      institution, read, createdAt }
  favorites/{tenderId}            ← legacy, servis okumaz
```

Servis kaynak listesi:
- `list_active_users_with_fcm()` — `isActive != false`, `fcmToken != null`; `ONLY_BETA_USERS=true` ise `isBeta=true` filtresi.
- `iter_user_alarms(uid)`, `iter_user_saved_filters(uid)` — alt koleksiyonları async iter eder.
- `write_notification(uid, payload)` — `notifications/` koleksiyonuna yeni belge ekler.
- `mark_alarm_completed(uid, tender_id)` — alarm belgesinde `completed=true`.
- `clear_fcm_token(uid)` — `UNREGISTERED` hatasında token'ı null'lar.

## EKAP v2 İmzalama

Mobil `IhaleTakip/src/api/v1/calls.js` ile birebir uyumlu olmak zorundadır.

- Algoritma: **AES-192-CBC + PKCS7**
- Anahtar: UTF-8 `"Qm2LtXR0aByP69vZNKef4wMJ"` (24 byte)
- IV: 16 byte random; header olarak base64 iletilir
- Her istekte yeni GUID + yeni IV + şimdiki timestamp_ms

Header formatı:
```
api-version: v1
X-Custom-Request-Guid: <guid-string>
X-Custom-Request-R8id: base64(AES192-CBC(guid, key, iv))
X-Custom-Request-Siv:  base64(iv)
X-Custom-Request-Ts:   base64(AES192-CBC(timestamp_ms_string, key, iv))
```

Parity testi (`tests/test_ekap_crypto.py`) sabit triple ile Python çıktısını doğrular ve `scripts/node_crypto_reference.js` Node + `crypto-js` ile karşılaştırma yapar (opsiyonel).

## Yeni Job Ekleme

1. `app/jobs/<new_job>.py` dosyası aç, `BaseJob`'tan miras al, `async def _run(self, metrics)` implementle.
2. Gerekli bağımlılıkları constructor'a ekle (`ekap`, `state`, `dispatcher` vb.).
3. `app/scheduler/scheduler.py` içinde yeni cron ile `add_job` çağrısı ekle.
4. `app/main.py` içinde wiring (instantiate + `build_scheduler`'a geç).
5. `scripts/run_once.py` argparse choices'una ekle.
6. `tests/test_<new_job>.py` — en az bir happy-path integration testi.

## Yeni EKAP Endpoint Ekleme

1. `app/ekap/client.py` içinde yeni metod; `self._post(path, body)` kullan — böylece rate limit + retry + imzalama otomatik uygulanır.
2. Yanıt için `app/ekap/models.py`'de Pydantic model tanımla.
3. DEFAULT_SEARCH_BODY tarzı base body varsa, mobil `api.js`'den birebir kopyala.

## Secret Yönetimi

- `scripts/serviceAccountKey.json` **asla commit edilmez** (`.gitignore` + `.claudeignore` + `.dockerignore`).
- Mobil projeden (`IhaleTakip/scripts/serviceAccountKey.json`) kopyalanır; docker-compose bu dosyayı `/secrets/serviceAccountKey.json` olarak ro mount eder.
- `.env` de commit edilmez; `.env.example` template'tir.
- Loglarda PII redakte edilir — yeni log satırı eklerken açık token/email basma.

## APScheduler Kuralları

Tüm job'lar için:
- `max_instances=1` — overlap yok
- `coalesce=True` — missed runs birleştir
- `misfire_grace_time=3600` — 1 saat içinde restart olsa bile çalıştır

SIGTERM alındığında `scheduler.shutdown(wait=True)` çalışır; Docker stop grace 60s.

## Dikkat Noktaları

- Mobil notification payload formatı (`App.tsx` + `firestoreApi.js`) bu servis tarafından da üretilmeli: `{type: "tender", title, body, tenderId, tenderTitle, tenderIkn, institution, read: false, createdAt}`.
- FCM `data` alanı **tüm değerler string** olmalı (iOS uyumu).
- `ihaleDurum` "completed" eşlemesi: ID `{"4","5","10","15","20"}` ∨ `ihaleDurumAciklama` içinde `sonuç|sonuc|tamamlan|iptal` (lowercase karşılaştırma).
- `dokumanSayisi` değişmeden de doküman içeriği değişebilir; ileride `dokumanlar` listesinin hash'i eklenebilir.
- `ilan.gov.tr` için **hiçbir** client/config/dependency eklenmez.

## Kritik Dosyalar (Referans)

- Mobil signing kaynağı: `/Users/tinyfect/Desktop/IhaleTakip/src/api/v1/calls.js`
- Default search body: `/Users/tinyfect/Desktop/IhaleTakip/src/api/v1/api.js`
- Firestore şeması: `/Users/tinyfect/Desktop/IhaleTakip/src/api/v1/firestoreApi.js`
- Notification payload: `/Users/tinyfect/Desktop/IhaleTakip/App.tsx`
- Service account kaynağı: `/Users/tinyfect/Desktop/IhaleTakip/scripts/serviceAccountKey.json`

## Test Stratejisi

1. **Crypto parity** (`test_ekap_crypto.py`) — EN KRİTİK. Mobil ile byte-by-byte eşleşme. Kırılırsa EKAP isteklerimiz reddedilir.
2. **Rate limiter** (`test_rate_limiter.py`) — timing-based, flaky olmamalı.
3. **Dedup grouper** (`test_dedup_grouper.py`) — fingerprint stable olmalı.
4. **State store** (`test_state_store.py`) — fakeredis ile roundtrip.
5. **Dispatcher** (`test_notifications.py`) — idempotency, dry-run, invalid token clearing.
6. **Jobs** (`test_alarm_job.py`, `test_saved_filter_job.py`) — in-memory fakes ile tam akış.

## Deploy (Ubuntu)

```bash
git clone <repo> && cd ihaletakip-scheduler
cp .env.example .env && nano .env
cp /path/to/serviceAccountKey.json scripts/
docker compose build
docker compose up -d
docker compose logs -f scheduler
```

İlk hafta için `ONLY_BETA_USERS=true` ile canary yap.
