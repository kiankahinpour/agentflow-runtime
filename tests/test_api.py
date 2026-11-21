import pytest
from fastapi.testclient import TestClient
from agentflow_runtime import Store, Worker
from agentflow_runtime.adapters import echo
from agentflow_runtime.api import create_app

TOKEN='my-local-test-token-1234567890'
@pytest.fixture
def client(tmp_path):
    s=Store(tmp_path/'db');return TestClient(create_app(s,TOKEN)),s

def headers():return {'Authorization':'Bearer '+TOKEN}

def test_auth(client):
    c,_=client
    assert c.get('/health').status_code==200
    assert c.get('/api/jobs').status_code==401
    assert c.get('/api/jobs',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.get('/api/jobs',headers=headers()).json()==[]

def test_api_end_to_end(client):
    c,s=client;h=headers();j=c.post('/api/jobs',headers=h,json={'prompt':'hello','idem':'one'}).json()['id']
    assert c.post('/api/jobs',headers=h,json={'prompt':'hello','idem':'one'}).json()['id']==j
    assert c.post('/api/jobs',headers=h,json={'prompt':'changed','idem':'one'}).status_code==409
    assert Worker(s,{'echo':echo}).once()
    assert c.get('/api/jobs/'+j,headers=h).json()['result']=='hello'
    assert c.get('/api/jobs/'+j+'/events',headers=h).json()[-1]['kind']=='succeeded'
    assert 'lease_token' not in c.get('/api/jobs/'+j,headers=h).json()

def test_approval_guard(client):
    c,s=client;h=headers();j=c.post('/api/jobs',headers=h,json={'prompt':'review','adapter':'codex'}).json()['id']
    assert s.get(j)['state']=='waiting_approval';assert s.claim(['codex']) is None
    assert c.post('/api/jobs/'+j+'/approve',headers=h).status_code==200
    assert c.post('/api/jobs/'+j+'/cancel',headers=h).status_code==200
    assert c.post('/api/jobs/'+j+'/approve',headers=h).status_code==409

def test_validation(client):
    c,_=client
    for data in [{'prompt':' '},{'prompt':'x','max_attempts':11},{'prompt':'x','adapter':'shell'}]:assert c.post('/api/jobs',headers=headers(),json=data).status_code==422
    assert c.get('/api/jobs/missing',headers=headers()).status_code==404
    assert c.get('/').headers['X-Frame-Options']=='DENY'
    assert 'AgentFlow Runtime' in c.get('/').text
