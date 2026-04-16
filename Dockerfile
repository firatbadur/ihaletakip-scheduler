# Multi-stage build for IhaleTakip scheduler.
FROM python:3.11-slim AS builder

WORKDIR /build

# Build-time deps for cryptography + any native wheels we may need
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt


FROM python:3.11-slim AS runtime

# tini for PID 1, tzdata for Europe/Istanbul, ca-certs for TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --uid 1000 app

ENV TZ=Europe/Istanbul \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/app/.local/bin:$PATH

WORKDIR /app

COPY --from=builder --chown=app:app /root/.local /home/app/.local
COPY --chown=app:app app /app/app

RUN mkdir -p /data/logs /secrets && chown -R app:app /data /secrets

USER app

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "app.main"]
