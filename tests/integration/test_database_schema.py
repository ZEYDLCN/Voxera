import os
from uuid import uuid4

import pytest

pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import select, text

from voxera.core.config import Settings
from voxera.db import Database
from voxera.db.models import Product
from voxera.db.repositories.contracts import OrganizationCreate, ProductCreate
from voxera.db.repositories.sqlalchemy import (
    SqlAlchemyOrganizationRepository,
    SqlAlchemyProductRepository,
)

pytestmark = pytest.mark.integration


def _validated_test_url(variable_name: str) -> str:
    url = os.getenv(variable_name)
    if not url:
        pytest.skip(f"{variable_name} is not configured")
    database_name = url.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0]
    if not database_name.endswith("_test"):
        pytest.fail(f"database in {variable_name} must end with '_test'")
    return url


@pytest.fixture(scope="module")
def migrated_database_url() -> str:
    application_url = _validated_test_url("VOXERA_TEST_DATABASE_URL")
    admin_url = _validated_test_url("VOXERA_TEST_DATABASE_ADMIN_URL")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", admin_url)
    os.environ["VOXERA_DATABASE_URL"] = application_url
    os.environ["VOXERA_DATABASE_ADMIN_URL"] = admin_url
    command.upgrade(config, "head")
    return application_url


@pytest.mark.asyncio
async def test_repository_never_returns_another_tenants_product(
    migrated_database_url: str,
) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=migrated_database_url,
        secret_key="integration-test-secret",
        object_storage_secret_key="integration-storage-secret",
    )
    database = Database(settings)
    suffix = uuid4().hex[:12]

    try:
        async with database.session() as session:
            organizations = SqlAlchemyOrganizationRepository(session)
            first_org = await organizations.add(
                OrganizationCreate(name="First tenant", slug=f"first-{suffix}")
            )
            second_org = await organizations.add(
                OrganizationCreate(name="Second tenant", slug=f"second-{suffix}")
            )
            first_org_id = first_org.id
            second_org_id = second_org.id

        async with database.session(first_org_id) as session:
            first_products = SqlAlchemyProductRepository(session, first_org_id)
            first_product = await first_products.add(ProductCreate(name="First", key="first"))
            first_product_id = first_product.id

        async with database.session(second_org_id) as session:
            second_products = SqlAlchemyProductRepository(session, second_org_id)
            second_product = await second_products.add(ProductCreate(name="Second", key="second"))
            second_product_id = second_product.id

        async with database.session(first_org_id) as session:
            first_products = SqlAlchemyProductRepository(session, first_org_id)
            assert await first_products.get(first_product_id) is not None
            assert await first_products.get(second_product_id) is None

        async with database.session() as session:
            policies = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE policyname = 'tenant_isolation'"
                )
            )
            # memberships, products, sources, reviews, import_jobs, review_sentiments
            assert policies == 6
            is_superuser = await session.scalar(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
            if not is_superuser:
                hidden_product = await session.scalar(
                    select(Product).where(Product.id == first_product_id)
                )
                assert hidden_product is None
    finally:
        await database.dispose()
