from fastapi import APIRouter

from voxera.analytics.router import router as analytics_router
from voxera.health.router import router as health_router
from voxera.ingestion.router import router as ingestion_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(ingestion_router, prefix="/reviews", tags=["ingestion"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
