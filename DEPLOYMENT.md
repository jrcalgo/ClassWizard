# Deployment

ClassWizard runs with Docker Compose. Docker is the only thing you need to install; the chatbot's language model (Ollama) runs in its own container.

## First time

1. Create your settings file and set `POSTGRES_PASSWORD`:
   ```bash
   cp .env.example .env
   ```
2. Give Docker Desktop 8 GB of memory or more (Settings > Resources) for the default `qwen3:8b` model. With less, pick a smaller model (see [Chatbot model](#chatbot-model)).
3. Build and start everything:
   ```bash
   docker compose up --build
   ```

The first build takes ~10-15 minutes. The first start takes several more minutes while the catalog loads and the syllabi are embedded.

On the first start, the `ollama-pull` container also downloads the chatbot model (`qwen3:8b`, about 5 GB) into the `ollama` volume and then exits. The rest of the app works while it downloads; the chat panel answers once it finishes. Watch it with `docker compose logs -f ollama-pull`. Later starts skip the download.

When it's ready, `curl http://127.0.0.1:8000/health` returns `OK`. Then open http://127.0.0.1:8501.

## Chatbot model

`EXPLAIN_MODEL` in `.env` picks the model. Only Ollama models are allowed (`ollama_chat/...` or `ollama/...`), so student data never leaves your machine.

| Model | Download | Docker memory |
|:--|:--|:--|
| `ollama_chat/qwen3:8b` (default) | ~5 GB | 8 GB+ |
| `ollama_chat/qwen3:4b` | ~2.5 GB | 6 GB+ |
| `ollama_chat/qwen3:1.7b` | ~1.4 GB | 4 GB+ |

After changing it, run `docker compose up -d` again to pull the new model.

On CPU an answer can take a minute or more. The backend gives up after `EXPLAIN_TIMEOUT` seconds (default 180, keep it below 240) and shows the retrieved facts instead.

### Use an NVIDIA GPU

Much faster. Needs an NVIDIA driver plus Docker Desktop with WSL 2 (Windows) or the NVIDIA Container Toolkit (Linux):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Use Ollama on your own machine

If you already run Ollama outside Docker and have pulled the model, set this in `.env`:

```
OLLAMA_URL=http://host.docker.internal:11434
```

Then skip the bundled containers:

```bash
docker compose up -d --scale ollama=0 --scale ollama-pull=0
```

### Free the disk space

The model stays in the `ollama` volume. `docker compose down -v` deletes it along with the database.

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

This deletes all loaded data, then loads it again on the next start. It also deletes the downloaded chatbot model, which is downloaded again.

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
