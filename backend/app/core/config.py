import secrets
from typing import Annotated, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils import parse_cors


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
        list[AnyUrl] | str, BeforeValidator(parse_cors)
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

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "syslogs"

    CLICKHOUSE_URL: str = "http://localhost:8123"
    CLICKHOUSE_DB: str = "netops"
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""

    LOG_QA_TOP_K: int = 8
    LOG_QA_EVENT_TOP_K: int = 20
    LOG_QA_LOOKBACK_SECONDS: int = 86_400
    LOG_QA_PROVIDER: Literal["gemini", "openai"] = "gemini"
    LOG_QA_MODEL: str = "gemini-2.5-flash-lite"

    GEMINI_MODEL: str = "GEMINI_MODEL"
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_INPUT_COST_PER_1M_TOKENS: float = 0.0
    OPENAI_OUTPUT_COST_PER_1M_TOKENS: float = 0.0
    GEMINI_INPUT_COST_PER_1M_TOKENS: float = 0.0
    GEMINI_OUTPUT_COST_PER_1M_TOKENS: float = 0.0

    LLM_CONTEXT_WINDOW: int = 100_000
    CHAT_ATTACHMENT_MAX_COUNT: int = 5
    CHAT_ATTACHMENT_MAX_BYTES: int = 262_144
    CHAT_ATTACHMENT_MAX_CHARS: int = 20_000
    CHAT_ATTACHMENT_MAX_TOTAL_CHARS: int = 40_000

    @computed_field  # type: ignore[misc]
    @property
    def get_gemini_api(self) -> str:
        if not self.GEMINI_API_KEY:
            raise Exception("No token provided for Gemini model.")
        return self.GEMINI_API_KEY

    TOOLS_USE_MOCK_DATA: bool = True

    if TOOLS_USE_MOCK_DATA:
        print("======================== USING MOCK DATA !!!")

    ZABBIX_ENABLED: bool = False
    BITBUCKET_ENABLED: bool = False
    SERVICENOW_ENABLED: bool = False

    BITBUCKET_CLONE_DIR: str = ""
    BITBUCKET_URL: str = ""

    ZABBIX_API_URL: str = ""
    ZABBIX_API_TOKEN: str = ""
    ZABBIX_TIMEOUT_SECONDS: float = 12.0

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


project_settings = Settings()  # type: ignore
