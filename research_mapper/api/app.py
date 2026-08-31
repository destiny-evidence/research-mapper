"""The API application."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from research_mapper import workflows
from research_mapper.api.routers import operations, sessions
from research_mapper.config import close_database, init_database, load_environment


def cors_origins() -> list[str]:
    """Origins allowed to call the API cross-origin."""
    raw = os.environ.get("MAPPER_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def configure_cors(app: FastAPI) -> None:
    """Allow the configured origins to call the API."""
    origins = cors_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["authorization", "content-type"],
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Open the database on boot."""
    load_environment()
    init_database()
    workflows.load()
    yield
    close_database()


load_environment()

app = FastAPI(title="research-mapper", lifespan=lifespan)
configure_cors(app)
app.include_router(sessions.router)
app.include_router(operations.router)
for workflow_router in workflows.routers():
    app.include_router(workflow_router)


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Liveness. Deliberately touches nothing."""
    return {"status": "ok"}
