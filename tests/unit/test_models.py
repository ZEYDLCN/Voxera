from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from voxera.db.models import Base


def test_core_schema_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "import_jobs",
        "memberships",
        "organizations",
        "products",
        "review_sentiments",
        "reviews",
        "sources",
        "users",
    }


def test_every_tenant_table_has_organization_id() -> None:
    for table_name in (
        "import_jobs",
        "memberships",
        "products",
        "review_sentiments",
        "reviews",
        "sources",
    ):
        assert "organization_id" in Base.metadata.tables[table_name].columns


def test_review_rating_constraint_is_registered() -> None:
    constraints = {constraint.name for constraint in Base.metadata.tables["reviews"].constraints}

    assert "ck_reviews_rating_range" in constraints


def test_core_schema_compiles_for_postgresql() -> None:
    dialect = postgresql.dialect()

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in ddl

    organization_ddl = str(
        CreateTable(Base.metadata.tables["organizations"]).compile(dialect=dialect)
    )
    assert "status IN ('active', 'suspended')" in organization_ddl
