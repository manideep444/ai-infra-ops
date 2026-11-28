FROM python:3.12-alpine@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS base
RUN apk upgrade --no-cache

FROM base AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

FROM base
RUN addgroup -S -g 10001 airp && adduser -S -D -H -u 10001 -G airp airp
COPY --from=builder /build/.venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY policies ./policies
COPY demo ./demo
COPY LICENSE ./LICENSE
USER 10001:10001
ENTRYPOINT ["python", "-m", "airp.cli"]