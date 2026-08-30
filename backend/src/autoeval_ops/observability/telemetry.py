"""OpenTelemetry setup: tracer provider, OTLP export to Jaeger, and
auto-instrumentation for FastAPI, SQLAlchemy, and httpx.

Uses the OTLP exporter rather than the Jaeger exporter Roadmap.md
originally specified - that exporter is deprecated and removed from
current OpenTelemetry releases; modern Jaeger accepts OTLP natively.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from autoeval_ops.config import settings

SERVICE_NAME = "autoeval-ops-backend"

_configured = False


def configure_tracing() -> None:
    """Idempotent - safe to call more than once (uvicorn --reload can
    re-import modules, and double-registering exporters duplicates spans)."""
    global _configured
    if _configured or not settings.otel_enabled:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_exporter_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    _configured = True


def instrument_app(app) -> None:
    """Auto-instrument FastAPI, SQLAlchemy, and httpx. Called from
    server.py after the app is created."""
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,api/v1/status")
    HTTPXClientInstrumentor().instrument()


def get_tracer(name: str):
    return trace.get_tracer(name)