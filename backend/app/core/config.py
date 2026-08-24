import secrets
from typing import Annotated, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors(value: object) -> list[str] | str:
    if isinstance(value, str) and not value.startswith("["):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | str):
        return value
    raise ValueError(value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(_parse_cors)
    ] = []

    @computed_field  # type: ignore[misc]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str

    ADMIN_USERNAME: str = ""
    ADMIN_PASS: str = ""

    SQLALCHEMY_URL: str = "sqlite+aiosqlite:///./netai_local.db"

    CLICKHOUSE_URL: str = "http://localhost:8123"
    CLICKHOUSE_DB: str = "netops"
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""

    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str | None = None

    LLM_CONTEXT_WINDOW: int = 100_000
    CHAT_ATTACHMENT_MAX_COUNT: int = 5
    CHAT_ATTACHMENT_MAX_BYTES: int = 262_144
    CHAT_ATTACHMENT_MAX_CHARS: int = 20_000
    CHAT_ATTACHMENT_MAX_TOTAL_CHARS: int = 40_000

    TOOLS_USE_MOCK_DATA: bool = True

    ZABBIX_ENABLED: bool = False
    SUZIEQ_ENABLED: bool = False
    BITBUCKET_ENABLED: bool = False
    SERVICENOW_ENABLED: bool = False

    INFRAHUB_MCP_URL: str = "http://127.0.0.1:8001/mcp"
    INFRAHUB_MCP_TOKEN: str = ""
    INFRAHUB_MCP_TIMEOUT_SECONDS: float = 5.0
    INFRAHUB_MCP_RESOURCE_TTL_SECONDS: float = 60.0
    SUZIEQ_MCP_URL: str = "http://127.0.0.1:8002/mcp"
    SUZIEQ_MCP_TOKEN: str = ""
    SUZIEQ_MCP_TIMEOUT_SECONDS: float = 5.0
    SUZIEQ_MCP_RESOURCE_TTL_SECONDS: float = 60.0
    MCP_CONSUMER_TOKEN: str = ""

    BITBUCKET_CLONE_DIR: str = ""
    BITBUCKET_URL: str = ""

    ZABBIX_API_URL: str = ""
    ZABBIX_API_TOKEN: str = ""
    ZABBIX_TIMEOUT_SECONDS: float = 12.0

    SUZIEQ_API_URL: str = "https://localhost:8000"
    SUZIEQ_API_TOKEN: str = ""
    SUZIEQ_TIMEOUT_SECONDS: float = 12.0
    SUZIEQ_VERIFY_TLS: bool = False

    SERVICENOW_INSTANCE_URL: str = ""
    SERVICENOW_API_VERSION: str = "v2"
    SERVICENOW_ACCESS_TOKEN: str = ""
    SERVICENOW_USERNAME: str = ""
    SERVICENOW_PASSWORD: str = ""
    SERVICENOW_TIMEOUT_SECONDS: float = 12.0

    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "http://localhost:3002"
    LANGFUSE_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)

    OTEL_TRACING_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_TRACES_HEADERS: str = ""
    OTEL_SERVICE_NAME: str = "netai"
    OTEL_TRACE_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)
    HAYSTACK_CONTENT_TRACING_ENABLED: bool = False


project_settings = Settings()  # type: ignore
