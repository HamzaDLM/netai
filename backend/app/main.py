from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import project_settings
from app.db.init_db import init_db
from app.db.session import close_engine
from app.observability import langfuse_client
from app.utils import warmup_caches


def custom_generate_unique_id(route: APIRoute) -> str:
    primary_tag = route.tags[0] if route.tags else "default"
    return f"{primary_tag}-{route.name}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    warmup_caches()
    yield
    langfuse_client.shutdown()
    await close_engine()


app = FastAPI(
    title=project_settings.PROJECT_NAME,
    openapi_url=f"{project_settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
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
