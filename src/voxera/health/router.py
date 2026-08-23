from fastapi import APIRouter, Request, Response, status

from voxera import __version__
from voxera.core.config import Settings
from voxera.db import Database
from voxera.health.schemas import ComponentHealth, HealthResponse, HealthStatus

router = APIRouter()


@router.get("/live", response_model=HealthResponse)
async def liveness(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status=HealthStatus.OK,
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    settings: Settings = request.app.state.settings
    components = {"configuration": ComponentHealth(status=HealthStatus.OK)}
    overall_status = HealthStatus.OK

    if settings.check_database_readiness:
        database: Database = request.app.state.database
        try:
            await database.ping()
            components["database"] = ComponentHealth(status=HealthStatus.OK)
        except Exception:
            overall_status = HealthStatus.ERROR
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            components["database"] = ComponentHealth(
                status=HealthStatus.ERROR,
                detail="database unavailable",
            )

    return HealthResponse(
        status=overall_status,
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
        components=components,
    )
