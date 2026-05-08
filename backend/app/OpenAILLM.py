"""Standalone example of a rotating-token OpenAI Haystack chat generator.

This file is intentionally not wired into the app yet. The important idea is
that agents keep a stable `llm` object, while auth refresh decisions stay inside
the auth provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from haystack import component
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.core.serialization import default_from_dict, default_to_dict
from haystack.dataclasses import ChatMessage
from haystack.utils.auth import Secret
from openai import APIStatusError, AuthenticationError


@dataclass(frozen=True)
class AuthToken:
    """Access token returned by your internal auth service."""

    value: str
    expires_at: datetime


class AuthProvider(Protocol):
    """Implement this with your real rotating-token source."""

    def get_token(self, *, force_refresh: bool = False) -> AuthToken:
        """Return a valid token.

        The provider owns refresh/staleness logic. `force_refresh=True` is used
        after an auth failure so the provider can bypass any cached token.
        """


class MockAuthProvider:
    """Mock provider that returns fake OpenAI-looking keys.

    This lets the component initialize and reach the outbound OpenAI request
    step. The request is still expected to fail because the token is fake.
    """

    def __init__(self, *, token_lifetime: timedelta = timedelta(minutes=30)) -> None:
        self.token_lifetime = token_lifetime
        self.refresh_skew = timedelta(minutes=5)
        self._lock = RLock()
        self._token: AuthToken | None = None
        self._issue_count = 0

    def get_token(self, *, force_refresh: bool = False) -> AuthToken:
        with self._lock:
            if force_refresh or self._token is None or self._token_is_stale():
                self._issue_count += 1
                self._token = AuthToken(
                    value=f"fake-{self._issue_count}",
                    expires_at=datetime.now(UTC) + self.token_lifetime,
                )
            return self._token

    def _token_is_stale(self) -> bool:
        if self._token is None:
            return True
        return datetime.now(UTC) >= self._token.expires_at - self.refresh_skew


@component
class ChatGen:
    """Haystack Agent-compatible wrapper around OpenAIChatGenerator.

    The wrapper itself is long-lived and safe to share at module scope. It asks
    the auth provider for a token on each run and rebuilds the inner
    OpenAIChatGenerator only when the provider returns a different token value.
    """

    def __init__(
        self,
        *,
        auth_provider: AuthProvider | None = None,
        model: str,
        generation_kwargs: dict[str, Any] | None = None,
        api_base_url: str | None = None,
        organization: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        http_client_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.auth_provider = auth_provider or MockAuthProvider()
        self.model = model
        self.generation_kwargs = generation_kwargs or {}
        self.api_base_url = api_base_url
        self.organization = organization
        self.timeout = timeout
        self.max_retries = max_retries
        self.http_client_kwargs = http_client_kwargs

        self._lock = RLock()
        self._token_value: str | None = None
        self._generator: OpenAIChatGenerator | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize only stable configuration, not the current token/client.

        The auth provider is intentionally omitted. If this component is
        deserialized by Haystack, it will fall back to MockAuthProvider. For a
        real custom provider, serialize provider config or use a provider
        registry here instead.
        """

        return default_to_dict(
            self,
            model=self.model,
            generation_kwargs=self.generation_kwargs,
            api_base_url=self.api_base_url,
            organization=self.organization,
            timeout=self.timeout,
            max_retries=self.max_retries,
            http_client_kwargs=self.http_client_kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatGen":
        """Deserialize using the stable config emitted by `to_dict()`."""

        return default_from_dict(cls, data)

    def warm_up(self) -> None:
        """Match Haystack's chat generator interface."""

        self._get_generator()

    @component.output_types(replies=list[ChatMessage])
    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Any | None = None,
        generation_kwargs: dict[str, Any] | None = None,
        *,
        tools: Any | None = None,
        tools_strict: bool | None = None,
    ) -> dict[str, list[ChatMessage]]:
        """Delegate to the current OpenAIChatGenerator.

        The `tools` keyword is required by Haystack's Agent component.
        """

        generator = self._get_generator()
        try:
            return generator.run(
                messages=messages,
                streaming_callback=streaming_callback,
                generation_kwargs=generation_kwargs,
                tools=tools,
                tools_strict=tools_strict,
            )
        except (AuthenticationError, APIStatusError) as exc:
            if not self._is_auth_error(exc):
                raise

            # The provider owns refresh behavior. We only request a forced token
            # lookup after auth failure, rebuild the client if needed, and retry.
            generator = self._get_generator(force_refresh=True)
            return generator.run(
                messages=messages,
                streaming_callback=streaming_callback,
                generation_kwargs=generation_kwargs,
                tools=tools,
                tools_strict=tools_strict,
            )

    def _get_generator(self, *, force_refresh: bool = False) -> OpenAIChatGenerator:
        with self._lock:
            token = self.auth_provider.get_token(force_refresh=force_refresh)
            if self._generator is None or token.value != self._token_value:
                self._token_value = token.value
                self._generator = OpenAIChatGenerator(
                    api_key=Secret.from_token(token.value),
                    model=self.model,
                    generation_kwargs=self.generation_kwargs,
                    api_base_url=self.api_base_url,
                    organization=self.organization,
                    timeout=self.timeout,
                    max_retries=self.max_retries,
                    http_client_kwargs=self.http_client_kwargs,
                )
            return self._generator

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        if isinstance(exc, AuthenticationError):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in {401, 403}
        return False


# Example only. Do not import this from the current app until we intentionally
# replace the existing Gemini `llm` wiring.
llm = ChatGen(
    auth_provider=MockAuthProvider(),
    model=os.environ.get("OPENAI_MODEL", "gpt-5-mini"),
    generation_kwargs={"temperature": 0.1},
    timeout=10.0,
    max_retries=0,
)

print(llm.run(messages=[ChatMessage.from_user("hey")]))
