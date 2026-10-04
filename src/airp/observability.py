import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from opentelemetry import trace
from prometheus_client import REGISTRY, Counter, Histogram, write_to_textfile

AGENTS = Counter("airp_agent_executions_total", "Agent calls", ["agent", "outcome"])
DURATION = Histogram("airp_agent_duration_seconds", "Agent duration", ["agent"])
WORKFLOWS = Counter("airp_workflows_total", "Workflow terminal observations", ["state"])
REMEDIATIONS = Counter("airp_remediations_total", "Executor outcomes", ["outcome"])
EXECUTION = Histogram("airp_remediation_duration_seconds", "Execution and validation latency")
LOG = logging.getLogger("airp")


def configure() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "airp"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)


def event(kind: str, run_id: str, **fields: str) -> None:
    LOG.info(json.dumps({"event": kind, "run_id": run_id, **fields}, sort_keys=True))


@contextmanager
def agent_span(name: str, run_id: str) -> Iterator[None]:
    started = time.monotonic()
    with trace.get_tracer("airp").start_as_current_span(name) as span:
        span.set_attribute("airp.run_id", run_id)
        try:
            yield
            AGENTS.labels(name, "success").inc()
            event("agent_completed", run_id, agent=name)
        except Exception:
            AGENTS.labels(name, "failure").inc()
            event("agent_failed", run_id, agent=name)
            raise
        finally:
            DURATION.labels(name).observe(time.monotonic() - started)


def export_metrics(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_to_textfile(path, registry=REGISTRY)
