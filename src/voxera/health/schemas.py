from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
    service: str
    version: str
    environment: str
    components: dict[str, ComponentHealth] = Field(default_factory=dict)

