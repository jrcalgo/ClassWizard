from classwizard import ai
from test_engine import c
import json
import pytest

@pytest.mark.parametrize('generated',[{'text':'Unsupported recommendation','citations':['FAKE 9999']},[],None])
def test_invalid_citation_falls_back_without_sending_private_properties(monkeypatch,generated):
    monkeypatch.setattr(ai,'retrieve_public',lambda *args:[])
    monkeypatch.setattr(ai,'model_guard',lambda *args:None)
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps(generated)}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            assert 'private-student-marker' not in str(kwargs)
            return Response()
    monkeypatch.setattr(ai.httpx,'Client',Client)
    course=c('TEST 1000');course['private_note']='private-student-marker'
    result=ai.explain([course],'fixture')
    assert result['mode']=='template'
    assert result['explanations'][0]['evidence']
