import base64

from app.core.config import Settings
from app.observability.tracing import _exporter_config, _headers


def test_langfuse_uses_otlp_without_sdk_dependency() -> None:
    settings = Settings(
        PROJECT_NAME="test",
        LANGFUSE_ENABLED=True,
        LANGFUSE_PUBLIC_KEY="public",
        LANGFUSE_SECRET_KEY="secret",
        LANGFUSE_BASE_URL="https://langfuse.example",
        LANGFUSE_SAMPLE_RATE=0.25,
    )

    config = _exporter_config(settings)

    assert config is not None
    endpoint, headers, sample_rate = config
    encoded = base64.b64encode(b"public:secret").decode()
    assert endpoint == "https://langfuse.example/api/public/otel/v1/traces"
    assert headers["Authorization"] == f"Basic {encoded}"
    assert sample_rate == 0.25


def test_generic_otel_headers_are_explicitly_parsed() -> None:
    assert _headers("Authorization=Bearer token,X-Tenant=netai") == {
        "Authorization": "Bearer token",
        "X-Tenant": "netai",
    }
