from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from fastapi_insights import Config, FastAPIInsights
from fastapi_insights.backends.in_memory import InMemoryMetricsStore
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import project_settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.db.session import close_engine
from app.observability import configure_tracing
from app.services.evals import EvalService
from app.services.netai import NetAIService

configure_logging()


def custom_generate_unique_id(route: APIRoute) -> str:
    primary_tag = route.tags[0] if route.tags else "default"
    return f"{primary_tag}-{route.name}"


@asynccontextmanager
async def lifespan(application: FastAPI):
    tracer_provider = configure_tracing(project_settings)
    netai_service: NetAIService | None = None
    eval_service: EvalService | None = None
    try:
        await init_db()
        netai_service = NetAIService(settings=project_settings)
        application.state.netai_service = netai_service
        await netai_service.warm_up()
        eval_service = EvalService(
            settings=project_settings, netai_service=netai_service
        )
        application.state.eval_service = eval_service
        await eval_service.warm_up()
        yield
    finally:
        try:
            if eval_service is not None:
                try:
                    await eval_service.close()
                finally:
                    delattr(application.state, "eval_service")
        finally:
            try:
                if netai_service is not None:
                    try:
                        await netai_service.close()
                    finally:
                        delattr(application.state, "netai_service")
            finally:
                await close_engine()
                if tracer_provider is not None:
                    tracer_provider.shutdown()


app = FastAPI(
    title=project_settings.PROJECT_NAME,
    openapi_url=f"{project_settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.request_id = request_id
    tracer = trace.get_tracer("netai.fastapi")
    with tracer.start_as_current_span(
        f"{request.method} {request.url.path}",
        kind=SpanKind.SERVER,
        attributes={
            "http.request.method": request.method,
            "url.path": request.url.path,
            "netai.request_id": request_id,
        },
    ) as span:
        try:
            response = await call_next(request)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        span.set_attribute("http.response.status_code", response.status_code)
        if response.status_code >= 500:
            span.set_status(Status(StatusCode.ERROR))
    response.headers["X-Request-ID"] = request_id
    return response


FastAPIInsights.init(
    app,
    InMemoryMetricsStore(),
    config=Config(custom_path="/insights"),
)

if project_settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=project_settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=project_settings.API_V1_STR)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def run_api():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
