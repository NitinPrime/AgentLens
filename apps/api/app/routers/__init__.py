from fastapi import APIRouter

from app.routers import (
    analytics,
    auth,
    evaluations,
    live,
    organizations,
    projects,
    sdk,
    system,
    traces,
    users,
    versions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(sdk.router)
api_router.include_router(evaluations.sdk_router)
api_router.include_router(traces.ingest_router)
api_router.include_router(traces.traces_router)
api_router.include_router(analytics.router)
api_router.include_router(evaluations.router)
api_router.include_router(versions.router)
api_router.include_router(live.router)
api_router.include_router(system.router)
