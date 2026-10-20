import os

ATTEMPT = os.getenv('ATTEMPT', 'v1')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://wizard:wizard@localhost:5432/wizard')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
DATA_DIR = os.getenv('DATA_DIR', '/data')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://ollama:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')
EMBEDDING_URL = os.getenv('EMBEDDING_URL', 'http://embeddings:8000')
