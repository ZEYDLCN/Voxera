from enum import Enum, StrEnum


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SourceType(StrEnum):
    CSV = "csv"
    JSON = "json"
    API = "api"
    GOOGLE_PLAY = "google_play"
    APP_STORE = "app_store"
    SUPPORT = "support"
    SURVEY = "survey"
    OTHER = "other"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    REJECTED = "rejected"
