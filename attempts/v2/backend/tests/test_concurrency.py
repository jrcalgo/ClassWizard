import copy
import json
import os
import pytest
from fastapi import HTTPException
from classwizard import sessions
from classwizard.db import public_snapshot, metrics

pytestmark=pytest.mark.skipif(os.getenv('INTEGRATION')!='1',reason='Requires ephemeral integration services')

def test_compare_and_set_and_deleted_result():
    token=sessions.create()
    first=sessions.get(token);second=copy.deepcopy(first)
    first['state']={'reviewed':True};sessions.save(token,first)
    with pytest.raises(HTTPException) as exc:
        sessions.save(token,second)
    assert exc.value.status_code==409
    revision=sessions.get(token)['revision']
    assert sessions.put_cache(token,'plans',revision,'v',{'status':'valid'})
    assert sessions.cached(token,'plans',revision,'v')=={'status':'valid'}
    sessions.delete(token)
    assert not sessions.put_cache(token,'plans',revision,'v',{'status':'valid'})
    assert not sessions.store.exists('session:'+token+':plans')

def test_job_registration_preserves_json_arrays_and_revision():
    token=sessions.create();data=sessions.get(token)
    data['state']={'in_progress':[], 'satisfied_groups':[], 'approved_exceptions':[]}
    sessions.save(token,data)
    revision=data['revision'];job={'owner':token,'revision':revision,'status':'pending'}
    sessions.add_job(token,data,'synthetic-job',job)
    after=sessions.get(token)
    assert after['revision']==revision
    assert after['state']['in_progress']==[]
    sessions.delete(token)
    assert not sessions.complete_job(token,'synthetic-job',revision,{**job,'status':'complete'})
    assert not sessions.store.exists('job:synthetic-job')

def test_public_snapshot_cache_only_checks_version_on_warm_reads():
    a=public_snapshot();before=metrics['queries'];b=public_snapshot()
    assert a is b
    assert metrics['queries']-before==1
