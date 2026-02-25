# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest@sha256:2f2ccd27bbf953ec7a9e3153a4563705e41c852a5e1912b438fc44d88d6cb52c /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE=copy \
  UV_PYTHON_DOWNLOADS=never \
  PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
  build-essential \
  git \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

# Strip binaries to save another ~50-100MB
# RUN find .venv/lib -name "*.so" -exec strip --strip-unneeded {} +

# ==========================================
# Stage 2: Runtime
# ==========================================
FROM python:3.13-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y \
  libpq5 \
  netcat-openbsd \
  curl \
  && rm -rf /var/lib/apt/lists/*

# 1. Create the user first
RUN groupadd -g 1000 verve && \
  useradd -u 1000 -g verve -s /bin/bash verve

WORKDIR /app

# 2. COPY --chown (Fixes the 384MB duplication)
COPY --from=builder --chown=verve:verve /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV UVICORN_TIMEOUT=30
ENV UVICORN_WORKERS=1

# 3. COPY --chown (For your code)
COPY --chown=verve:verve . /app

# 4. Copy scripts (ownership doesn't matter much for /bin, but chmod is needed)
COPY docker-entrypoint.sh /usr/local/bin/
COPY run.sh /usr/local/bin/

# We only chmod here. We DO NOT run chown -R /app anymore.
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/run.sh

USER verve

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["run.sh"]
