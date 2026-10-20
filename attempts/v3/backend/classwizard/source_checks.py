"""Periodic public-source checks; changed academic rules require review before activation."""
import json
import re
import time
import uuid
from datetime import datetime,timezone
import httpx
from sqlalchemy import select
from .db import transaction,Dataset,IngestionRun

def check():
    with transaction() as session:
        current=session.execute(select(Dataset).where(Dataset.active==True)).scalar_one_or_none()
        if not current:return {'status':'not_initialized'}
        manifest=current.manifest
    with httpx.Client(timeout=30,follow_redirects=True) as client:
        response=client.get('https://www.onetcenter.org/database.html');response.raise_for_status()
        match=re.search(r'db_(\d+)_(\d+)_csv',response.text)
        latest='.'.join(match.groups()) if match else 'unknown'
        catalog=client.head(manifest['source_url']);catalog.raise_for_status()
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'onet_release':latest,
            'pinned_release':manifest['onet_release'],'requires_review':latest not in ('unknown',manifest['onet_release']),
            'catalog_url':manifest['source_url'],'catalog_headers':{k:v for k,v in catalog.headers.items() if k in ['etag','last-modified','content-length']},
            'activation':'Acquire public files, prepare, review quality/rules, then run init. No automatic rule replacement.'}
    with transaction() as session:
        session.add(IngestionRun(id=str(uuid.uuid4()),payload={'type':'source_check',**result}))
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--loop',action='store_true');args=parser.parse_args()
    while True:
        try:print(json.dumps(check()),flush=True)
        except Exception as exc:print(json.dumps({'status':'source_check_failed','type':type(exc).__name__}),flush=True)
        if not args.loop:break
        # Checking daily observes annual catalog and quarterly O*NET changes without
        # modifying reviewed degree rules or generating speculative future catalog URLs.
        time.sleep(86400)
