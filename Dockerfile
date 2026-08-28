# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.7 AS uv

FROM python:3.12.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-default-groups --group seed

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group seed

FROM python:3.12.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN useradd --create-home --uid 10001 nexus

COPY --from=builder /app/.venv /app/.venv
COPY . .

USER nexus

EXPOSE 5000

CMD ["flask", "--app", "run.py", "run", "--host=0.0.0.0", "--port=5000"]
