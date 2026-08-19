"""Shared asynchronous infrastructure clients owned by the application lifespan."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from haystack.components.agents import State
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode


class InfrastructureClients:
    """Connection-pooled HTTP access with one span per external request."""

    def __init__(self) -> None:
        self.http = httpx.AsyncClient(follow_redirects=True)
        self.insecure_http = httpx.AsyncClient(
            follow_redirects=True,
            verify=False,
        )
        self._tracer = trace.get_tracer("netai.infrastructure")

    async def request(
        self,
        connector: str,
        method: str,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        content: str | bytes | None = None,
        json: object | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float | None = None,
        verify: bool = True,
    ) -> httpx.Response:
        with self._tracer.start_as_current_span(
            f"{connector}.http",
            kind=SpanKind.CLIENT,
            attributes={
                "server.address": httpx.URL(url).host,
                "http.request.method": method.upper(),
                "netai.connector": connector,
            },
        ) as span:
            try:
                client = self.http if verify else self.insecure_http
                request_kwargs: dict[str, Any] = {
                    "params": params,
                    "headers": headers,
                    "content": content,
                    "auth": auth,
                    "timeout": timeout,
                }
                if json is not None:
                    request_kwargs["json"] = json
                response = await client.request(method, url, **request_kwargs)
                span.set_attribute("http.response.status_code", response.status_code)
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR))
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    async def close(self) -> None:
        await self.http.aclose()
        await self.insecure_http.aclose()


def clients_from_state(state: State) -> InfrastructureClients:
    context = state.data.get("hook_context")
    clients = context.get("clients") if isinstance(context, dict) else None
    if not isinstance(clients, InfrastructureClients):
        raise RuntimeError(
            "Infrastructure clients are unavailable outside NetAIService"
        )
    return clients
