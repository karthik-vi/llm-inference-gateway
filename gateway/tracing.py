"""OpenTelemetry setup. GATEWAY_TRACE_FILE=path -> spans as JSON lines (used by the incident drill);
OTEL_EXPORTER_OTLP_ENDPOINT -> OTLP gRPC (needs opentelemetry-exporter-otlp; compose/k8s only).
With neither set the API is a no-op."""
from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_tracing() -> None:
    path = os.environ.get("GATEWAY_TRACE_FILE")
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not path and not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "llm-gateway"}))
    if path:
        f = open(path, "a", buffering=1)  # noqa: SIM115
        exporter = ConsoleSpanExporter(out=f, formatter=lambda s: s.to_json(indent=None) + "\n")
        provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=500))
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
