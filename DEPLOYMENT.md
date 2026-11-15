# Deployment

ClassWizard runs with Docker Compose. Docker must be running.

## First time

1. Create your settings file and set `POSTGRES_PASSWORD`:
   ```bash
   cp .env.example .env
   ```
2. If you use the default chat mode, start Ollama on your machine and pull the model:
   ```bash
   ollama pull qwen3:8b
   ```
3. Build and start everything:
   ```bash
   docker compose up --build
   ```

The first build takes ~10-15 minutes. The first start takes several more minutes while the catalog loads and the syllabi are embedded.

When it's ready, `curl http://127.0.0.1:8000/health` returns `OK`. Then open http://127.0.0.1:8501.

## Redeploy after a code change

```bash
docker compose up -d --build
```

Your database is kept, and only changed parts rebuild. Rebuilds take substantially less time than the initial build.

## Restart

```bash
docker compose down
docker compose up -d
```

## Start over with an empty database

This deletes all loaded data, then loads it again on the next start.

```bash
docker compose down -v
docker compose up -d --build
```

## Clear the build cache

```bash
docker compose down --rmi local
docker builder prune --all
```

## See the logs

```bash
docker compose logs -f backend
```
