FROM python:3.15-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853 AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

FROM python:3.15-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853
RUN groupadd --gid 10001 airp && useradd --uid 10001 --gid 10001 --no-create-home airp
COPY --from=builder /build/.venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY policies ./policies
COPY demo ./demo
COPY LICENSE ./LICENSE
USER 10001:10001
ENTRYPOINT ["python", "-m", "airp.cli"]