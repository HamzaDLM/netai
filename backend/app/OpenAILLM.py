"""Standalone example of a rotating-token OpenAI Haystack chat generator.

This file is intentionally not wired into the app yet. The important idea is
that agents keep a stable `llm` object, while this object swaps its internal
OpenAIChatGenerator whenever the bearer token is close to expiry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils.auth import Secret
from openai import APIStatusError, AuthenticationError


@dataclass(frozen=True)
class OpenAIToken:
    """Access token returned by your internal auth service."""

    value: str
    expires_at: datetime


class OpenAITokenProvider(Protocol):
    """Implement this with your real rotating-token source."""

    def get_token(self, *, force_refresh: bool = False) -> OpenAIToken:
        """Return a valid token.

        `force_refresh=True` is used after an auth failure so the provider does
        not return a cached token that may already have been rejected upstream.
        """


class EnvironmentTokenProvider:
    """Simple demo provider.

    Replace this with the work-version token fetcher, for example a call to an
    identity provider, vault, sidecar, or internal token broker.
    """

    def get_token(self, *, force_refresh: bool = False) -> OpenAIToken:
        _ = force_refresh
        token = os.environ["OPENAI_API_KEY"]
        return OpenAIToken(
            value=token,
            expires_at=datetime.now(UTC) + timedelta(minutes=25),
        )


class RotatingOpenAIChatGenerator:
    """Haystack Agent-compatible wrapper around OpenAIChatGenerator.

    The wrapper itself is long-lived and safe to share at module scope. It keeps
    an inner OpenAIChatGenerator only while the token is fresh.
    """

    def __init__(
        self,
        *,
        token_provider: OpenAITokenProvider,
        model: str,
        generation_kwargs: dict[str, Any] | None = None,
        api_base_url: str | None = None,
        organization: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        refresh_skew: timedelta = timedelta(minutes=5),
        http_client_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._model = model
        self._generation_kwargs = generation_kwargs or {}
        self._api_base_url = api_base_url
        self._organization = organization
        self._timeout = timeout
        self._max_retries = max_retries
        self._refresh_skew = refresh_skew
        self._http_client_kwargs = http_client_kwargs

        self._lock = RLock()
        self._token: OpenAIToken | None = None
        self._generator: OpenAIChatGenerator | None = None

    def warm_up(self) -> None:
        """Match Haystack's chat generator interface."""

        self._get_generator()

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

            # Token was rejected despite the proactive refresh window. Refresh
            # once and retry the request.
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
            if force_refresh or self._generator is None or self._token_is_stale():
                token = self._token_provider.get_token(force_refresh=force_refresh)
                self._token = token
                self._generator = OpenAIChatGenerator(
                    api_key=Secret.from_token(token.value),
                    model=self._model,
                    generation_kwargs=self._generation_kwargs,
                    api_base_url=self._api_base_url,
                    organization=self._organization,
                    timeout=self._timeout,
                    max_retries=self._max_retries,
                    http_client_kwargs=self._http_client_kwargs,
                )
            return self._generator

    def _token_is_stale(self) -> bool:
        if self._token is None:
            return True
        return datetime.now(UTC) >= self._token.expires_at - self._refresh_skew

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        if isinstance(exc, AuthenticationError):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in {401, 403}
        return False


# Example only. Do not import this from the current app until we intentionally
# replace the existing Gemini `llm` wiring.
llm = RotatingOpenAIChatGenerator(
    token_provider=EnvironmentTokenProvider(),
    model=os.environ.get("OPENAI_MODEL", "gpt-5-mini"),
    generation_kwargs={"temperature": 0.1},
)
