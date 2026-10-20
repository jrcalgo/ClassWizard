"""Synthetic end-to-end evidence validation; no real worksheets or session identifiers saved."""
import json
import time
from pathlib import Path
import httpx
from classwizard.models import Preferences

with httpx.Client(base_url='http://api:8000',timeout=30) as client:
    client.post('/api/v1/sessions').raise_for_status()
    try:
        state=json.loads(Path('/demo-state.json').read_text())
        client.put('/api/v1/academic-state',json=state).raise_for_status()
        client.put('/api/v1/preferences',json=Preferences(min_courses=0,min_credits=0).model_dump()).raise_for_status()
        started=time.monotonic()
        job=client.post('/api/v1/explanations');job.raise_for_status();jobid=job.json()['job_id']
        while time.monotonic()-started<180:
            response=client.get('/api/v1/explanations/'+jobid);response.raise_for_status();data=response.json()
            if data['status']!='pending':break
            time.sleep(1)
        assert data['status']=='complete',data['status']
        report={'synthetic':True,'elapsed_seconds':time.monotonic()-started,'version':data['version'],'result':data['result']}
        assert report['result']['explanations']
        Path('/reports/ai-validation.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    finally:
        client.delete('/api/v1/session').raise_for_status()
