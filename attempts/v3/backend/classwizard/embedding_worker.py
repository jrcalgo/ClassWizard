"""Public-only ETL worker; cannot delay private explanation queue processing."""
import time
from .ai import build_embeddings
from .db import active_version

last_version=None
while True:
    try:
        version=active_version()
        if version and version!=last_version:
            count=build_embeddings()
            print(f'Public embedding pass: {count} new chunks',flush=True)
            last_version=version
        time.sleep(30)
    except Exception as exc:
        print(f'Public embedding pass failed ({type(exc).__name__}); retry in 15 seconds.',flush=True)
        time.sleep(15)
