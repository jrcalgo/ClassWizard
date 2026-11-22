"""Lifecycle checks use injected events rather than wall-clock sleeps."""
import sys
import pytest
pytest.importorskip('psycopg')
pytest.importorskip('pyspark')
from ai.recommendations.spark_jobs import worker


def test_backoff_caps_at_fifteen_minutes():
    assert [worker.retry_delay(i) for i in range(8)]==[30,60,120,240,480,900,900,900]


def test_worker_rechecks_freshness_before_every_retry(monkeypatch,tmp_path):
    calls=[]
    class Event:
        done=False
        def is_set(self): return self.done
        def wait(self,seconds):
            calls.append(seconds)
            if len(calls)==8: self.done=True
        def set(self): self.done=True
    event=Event()
    monkeypatch.setattr(worker,'stop',event)
    monkeypatch.setattr(worker,'LAKE_DIR',tmp_path)
    monkeypatch.setattr(sys,'argv',['worker'])
    attempts=[]
    def attempt():
        attempts.append(True)
        if len(attempts)<8: raise RuntimeError('deliberate failure')
    monkeypatch.setattr(worker,'attempt',attempt)
    worker.main()
    assert len(attempts)==8
    assert calls==[30,60,120,240,480,900,900,30]


def test_duplicate_worker_exits_without_waiting(monkeypatch,tmp_path):
    monkeypatch.setattr(worker,'LAKE_DIR',tmp_path)
    monkeypatch.setattr(sys,'argv',['worker','--once'])
    def busy(*args): raise BlockingIOError()
    monkeypatch.setattr(worker.fcntl,'flock',busy)
    monkeypatch.setattr(worker,'attempt',lambda:pytest.fail('duplicate worker trained'))
    worker.main()
