FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd AS base
RUN apk upgrade --no-cache

FROM base AS builder
WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.13.10
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

FROM base
RUN addgroup -S -g 10001 airp && adduser -S -D -H -u 10001 -G airp airp
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY policies ./policies
COPY demo ./demo
COPY LICENSE ./LICENSE
USER 10001:10001
ENTRYPOINT ["python", "-m", "airp.cli"]