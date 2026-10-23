# Restore

Postgres runs inside the backend container. This dump replaces the catalog, program, and O*NET tables. Redis is not included.

```bash
docker compose up -d
docker compose exec -T backend psql -h 127.0.0.1 -U classwizard -d classwizard -v ON_ERROR_STOP=1 < database_dump/classwizard.sql
```

User, password, and database name default to `classwizard`.
