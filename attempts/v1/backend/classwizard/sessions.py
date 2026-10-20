import json
import secrets
import time
import redis
from fastapi import HTTPException
from .config import REDIS_URL

store = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
IDLE = 3600
ABSOLUTE = 8 * 3600

def create():
    token = secrets.token_urlsafe(32)
    data = {'created': time.time(), 'revision': 0, 'state': None, 'preferences': None, 'jobs': []}
    store.setex('session:' + token, IDLE, json.dumps(data))
    return token

def get(token):
    if not token or len(token) > 100:
        raise HTTPException(401, 'Start a new session.')
    raw = store.get('session:' + token)
    if not raw:
        raise HTTPException(401, 'Session expired. Student data has been deleted.')
    data = json.loads(raw)
    remaining = int(data['created'] + ABSOLUTE - time.time())
    if remaining <= 0:
        delete(token)
        raise HTTPException(401, 'Session expired.')
    store.expire('session:' + token, min(IDLE, remaining))
    return data

def save(token, data):
    remaining = int(data['created'] + ABSOLUTE - time.time())
    if remaining <= 0 or not store.exists('session:' + token):
        raise HTTPException(401, 'Session expired.')
    data['revision'] += 1
    store.setex('session:' + token, min(IDLE, remaining), json.dumps(data))

def delete(token):
    raw = store.get('session:' + token)
    if raw:
        for job in json.loads(raw).get('jobs', []):
            store.delete('job:' + job)
    store.delete('session:' + token)
