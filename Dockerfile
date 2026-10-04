FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
RUN groupadd --gid 10001 airp && useradd --uid 10001 --gid 10001 --no-create-home airp
COPY --from=builder /build/.venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY policies ./policies
COPY demo ./demo
COPY LICENSE ./LICENSE
USER 10001:10001
ENTRYPOINT ["python", "-m", "airp.cli"]