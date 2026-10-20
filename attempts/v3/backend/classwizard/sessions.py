"""Atomic Redis lifecycle. All private state and derived results are ephemeral."""
import json
import secrets
import time
import redis
from fastapi import HTTPException
from .config import REDIS_URL

store=redis.Redis.from_url(REDIS_URL,decode_responses=True,socket_timeout=3)
IDLE=3600
ABSOLUTE=8*3600

DELETE = '''local raw=redis.call('GET',KEYS[1]);
if raw then local d=cjson.decode(raw); for _,j in ipairs(d.jobs) do redis.call('DEL','job:'..j); redis.call('LREM','explanation_queue',0,j); redis.call('LREM','explanation_processing',0,j) end end;
redis.call('DEL',KEYS[1],KEYS[1]..':recommendations',KEYS[1]..':plans'); return 1'''
TOUCH = '''local raw=redis.call('GET',KEYS[1]); if not raw then return false end;
local d=cjson.decode(raw); local remaining=math.floor(d.created+tonumber(ARGV[2])-tonumber(ARGV[1]));
if remaining<=0 then for _,j in ipairs(d.jobs) do redis.call('DEL','job:'..j) end;
redis.call('DEL',KEYS[1],KEYS[1]..':recommendations',KEYS[1]..':plans'); return false end;
redis.call('EXPIRE',KEYS[1],math.min(remaining,tonumber(ARGV[3]))); return raw'''
SAVE = '''local raw=redis.call('GET',KEYS[1]); if not raw then return -1 end;
local old=cjson.decode(raw); if old.revision~=tonumber(ARGV[1]) then return -2 end;
local ttl=redis.call('TTL',KEYS[1]); if ttl<=0 then return -1 end;
local jobs='[]'; if #old.jobs>0 then jobs=cjson.encode(old.jobs) end;
local updated=string.gsub(ARGV[2],'"jobs"%s*:%s*%b[]','"jobs":'..jobs,1);
redis.call('SETEX',KEYS[1],ttl,updated);
redis.call('DEL',KEYS[1]..':recommendations',KEYS[1]..':plans'); return 1'''
CACHE = '''local raw=redis.call('GET',KEYS[1]); if not raw then return 0 end;
local d=cjson.decode(raw); if d.revision~=tonumber(ARGV[1]) then return 0 end;
local ttl=redis.call('TTL',KEYS[1]); if ttl<=0 then return 0 end;
redis.call('SETEX',KEYS[2],math.min(ttl,300),ARGV[2]); return 1'''
ADD_JOB = '''local raw=redis.call('GET',KEYS[1]); if not raw then return -1 end;
local d=cjson.decode(raw); if d.revision~=tonumber(ARGV[1]) then return -2 end;
if #d.jobs>=5 or redis.call('LLEN','explanation_queue')+redis.call('LLEN','explanation_processing')>=100 then return -3 end; table.insert(d.jobs,ARGV[2]);
local ttl=redis.call('TTL',KEYS[1]); if ttl<=0 then return -1 end;
local updated=string.gsub(raw,'"jobs"%s*:%s*%b[]','"jobs":'..cjson.encode(d.jobs),1);
redis.call('SETEX',KEYS[1],ttl,updated); redis.call('SETEX',KEYS[2],ttl,ARGV[3]);
redis.call('RPUSH','explanation_queue',ARGV[2]); return 1'''
COMPLETE = '''local raw=redis.call('GET',KEYS[1]); if not raw or redis.call('EXISTS',KEYS[2])==0 then return 0 end;
local d=cjson.decode(raw); if d.revision~=tonumber(ARGV[1]) then return 0 end;
local ttl=redis.call('TTL',KEYS[1]); if ttl<=0 then return 0 end;
redis.call('SETEX',KEYS[2],ttl,ARGV[2]); return 1'''

def create():
    token=secrets.token_urlsafe(32)
    data={'created':time.time(),'revision':0,'state':None,'preferences':None,'jobs':[]}
    store.setex('session:'+token,IDLE,json.dumps(data));return token

def get(token):
    if not token or len(token)>100:raise HTTPException(401,'Start a new session.')
    raw=store.eval(TOUCH,1,'session:'+token,time.time(),ABSOLUTE,IDLE)
    if not raw:raise HTTPException(401,'Session expired. Student data has been deleted.')
    data=json.loads(raw)
    if data.get('jobs')=={}:data['jobs']=[]
    return data

def save(token,data):
    revision=data['revision'];data['revision']+=1
    outcome=store.eval(SAVE,1,'session:'+token,revision,json.dumps(data))
    if outcome==-1:raise HTTPException(401,'Session expired.')
    if outcome==-2:raise HTTPException(409,'Your academic state changed in another request. Refresh and retry.')

def delete(token):
    store.eval(DELETE,1,'session:'+token)

def cached(token,endpoint,revision,version,serialized=False):
    raw=store.get('session:'+token+':'+endpoint)
    if raw:
        header,body=raw.split('\n',1)
        data=json.loads(header)
        if data['revision']==revision and data['version']==version:
            return body if serialized else json.loads(body)
    return None

def put_cache(token,endpoint,revision,version,result):
    return store.eval(CACHE,2,'session:'+token,'session:'+token+':'+endpoint,revision,
                      json.dumps({'revision':revision,'version':version},separators=(',',':'))+'\n'+json.dumps(result,separators=(',',':')))

def add_job(token,data,jobid,job):
    outcome=store.eval(ADD_JOB,2,'session:'+token,'job:'+jobid,data['revision'],jobid,json.dumps(job))
    if outcome==-1:raise HTTPException(401,'Session expired.')
    if outcome==-2:raise HTTPException(409,'Academic state changed; retry.')
    if outcome==-3:raise HTTPException(429,'Explanation queue is full or this session already has five jobs.')

def complete_job(token,jobid,revision,job):
    return store.eval(COMPLETE,2,'session:'+token,'job:'+jobid,revision,json.dumps(job))
