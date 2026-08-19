"""Explicit OpenTelemetry configuration shared by FastAPI and Haystack."""

from __future__ import annotations

import base64
import contextlib
import logging
from collections.abc import Iterator

from haystack import tracing as haystack_tracing
from haystack.tracing import Span, Tracer
from haystack.tracing import utils as tracing_utils
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import NonRecordingSpan

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OpenTelemetrySpan(Span):
    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def set_tag(self, key: str, value: object) -> None:
        self._span.set_attribute(key, tracing_utils.coerce_tag_value(value))

    def raw_span(self) -> trace.Span:
        return self._span

    def get_correlation_data_for_logs(self) -> dict[str, str]:
        context = self._span.get_span_context()
        if not context.is_valid:
            return {}
        return {
            "trace_id": format(context.trace_id, "032x"),
            "span_id": format(context.span_id, "016x"),
        }


class OpenTelemetryTracer(Tracer):
    """Small adapter from Haystack's tracing protocol to OpenTelemetry."""

    def __init__(self, tracer: trace.Tracer) -> None:
        self._tracer = tracer

    @contextlib.contextmanager
    def trace(
        self,
        operation_name: str,
        tags: dict[str, object] | None = None,
        parent_span: Span | None = None,
    ) -> Iterator[Span]:
        parent_context = None
        if parent_span is not None and isinstance(parent_span.raw_span(), trace.Span):
            parent_context = trace.set_span_in_context(parent_span.raw_span())
        with self._tracer.start_as_current_span(
            operation_name,
            context=parent_context,
        ) as raw_span:
            span = OpenTelemetrySpan(raw_span)
            if tags:
                span.set_tags(tags)
            yield span

    def current_span(self) -> Span | None:
        current = trace.get_current_span()
        if (
            isinstance(current, NonRecordingSpan)
            or not current.get_span_context().is_valid
        ):
            return None
        return OpenTelemetrySpan(current)


def _headers(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in value.split(","):
        key, separator, header_value = item.partition("=")
        if separator and key.strip():
            parsed[key.strip()] = header_value.strip()
    return parsed


def _exporter_config(
    settings: Settings,
) -> tuple[str, dict[str, str], float] | None:
    if (
        settings.LANGFUSE_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    ):
        credentials = base64.b64encode(
            f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
        ).decode()
        endpoint = f"{settings.LANGFUSE_BASE_URL.rstrip('/')}/api/public/otel/v1/traces"
        return (
            endpoint,
            {
                "Authorization": f"Basic {credentials}",
                "x-langfuse-ingestion-version": "4",
            },
            settings.LANGFUSE_SAMPLE_RATE,
        )

    if settings.OTEL_TRACING_ENABLED and settings.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:
        return (
            settings.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
            _headers(settings.OTEL_EXPORTER_OTLP_TRACES_HEADERS),
            settings.OTEL_TRACE_SAMPLE_RATE,
        )
    return None


def configure_tracing(settings: Settings) -> TracerProvider | None:
    """Configure one OTLP exporter and connect Haystack's native spans to it."""

    haystack_tracing.tracer.is_content_tracing_enabled = (
        settings.HAYSTACK_CONTENT_TRACING_ENABLED
    )
    exporter_config = _exporter_config(settings)
    if exporter_config is None:
        haystack_tracing.disable_tracing()
        logger.info("OpenTelemetry export disabled")
        return None

    endpoint, headers, sample_rate = exporter_config
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME}),
        sampler=TraceIdRatioBased(sample_rate),
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
    )
    trace.set_tracer_provider(provider)
    haystack_tracing.enable_tracing(
        OpenTelemetryTracer(provider.get_tracer("netai.haystack"))
    )
    logger.info("OpenTelemetry export enabled for %s", endpoint)
    return provider
