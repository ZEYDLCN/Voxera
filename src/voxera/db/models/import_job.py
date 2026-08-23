from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from voxera.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from voxera.db.models.enums import ImportFormat, ImportJobStatus, enum_values


class ImportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one asynchronous CSV/JSON review import from upload through completion.

    Upload -> object storage -> this row (status=pending) -> Celery worker picks it up
    -> ReviewImportService -> status=succeeded/failed. `dispatched_at` lets a periodic
    reconciliation job re-enqueue anything the direct post-commit enqueue call missed
    (process crash, broker hiccup) without a separate generic outbox table.
    """

    __tablename__ = "import_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_id", "product_id", "organization_id"],
            ["sources.id", "sources.product_id", "sources.organization_id"],
            ondelete="CASCADE",
        ),
        Index("ix_import_jobs_organization_status", "organization_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_format: Mapped[ImportFormat] = mapped_column(
        Enum(
            ImportFormat,
            name="import_format",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
    )
    status: Mapped[ImportJobStatus] = mapped_column(
        Enum(
            ImportJobStatus,
            name="import_job_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=32,
        ),
        default=ImportJobStatus.PENDING,
        server_default=text("'pending'"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_rows: Mapped[int | None] = mapped_column(Integer)
    imported_count: Mapped[int | None] = mapped_column(Integer)
    duplicate_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
