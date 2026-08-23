# Database migrations

Alembic reads the database URL from `VOXERA_DATABASE_URL`. Apply migrations with:

```bash
alembic upgrade head
```

Application queries to tenant tables must run through `Database.session(organization_id)`.
The transaction-local organization setting is consumed by PostgreSQL row-level security.

