from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from voxera import __version__
from voxera.api.middleware import RequestContextMiddleware
from voxera.api.router import api_router
from voxera.core.config import Settings, get_settings
from voxera.core.logging import configure_logging, get_logger
from voxera.db import Database
from voxera.services.task_queue import ImportJobQueue
from voxera.storage import S3ObjectStorage


def create_app(
    settings: Settings | None = None,
    *,
    import_job_queue: ImportJobQueue | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    `import_job_queue` is injected rather than constructed here: the concrete Celery
    adapter lives under `apps.worker`, and `voxera` (the framework-agnostic library)
    must not import from `apps` -- that dependency would run backwards. The real
    entrypoint (`apps.api.main`) wires `CeleryImportJobQueue` in; tests can pass a
    fake or leave it `None` if they never exercise the async import-job endpoints.
    """

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    logger = get_logger(__name__)
    database = Database(resolved_settings)
    object_storage = S3ObjectStorage(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            extra={"environment": resolved_settings.environment},
        )
        yield
        await database.dispose()
        logger.info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.object_storage = object_storage
    application.state.import_job_queue = import_job_queue
    application.add_middleware(RequestContextMiddleware)
    application.include_router(api_router)
    return application
