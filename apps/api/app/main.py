from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.core.observability import registry
from app.database import engine, init_db
from app.dependencies import close_redis
from app.middleware import ObservabilityMiddleware, RequestGuardMiddleware
from app.routers import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Registered inner to outer: CORS ends up outermost so even throttled or failed
# requests carry the headers a browser needs to read the response.
app.add_middleware(RequestGuardMiddleware)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "agentlens-api", "version": settings.app_version}


@app.get("/health/ready", tags=["system"])
async def readiness_check() -> JSONResponse:
    """Liveness plus a real dependency check, for load balancers and k8s probes."""

    database_ok = True
    detail: str | None = None
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        database_ok = False
        detail = f"{type(exc).__name__}: {exc}"

    return JSONResponse(
        status_code=200 if database_ok else 503,
        content={
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "unavailable",
            "detail": detail,
            "uptime_seconds": round(registry.uptime_seconds, 3),
        },
    )
