"""Reproducible signed-webhook -> approval -> DAG smoke demo. No network or real credentials."""
import hashlib,hmac,json,secrets,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from agentflow_runtime import Store,Worker
from agentflow_runtime.api import create_app
from agentflow_runtime.github import GitHubIntake
from agentflow_runtime.plugins import default_registry
from agentflow_runtime.workflows import Workflows

def main():
    with tempfile.TemporaryDirectory() as d:
        store=Store(Path(d)/'queue.db');secret=secrets.token_urlsafe(32);token=secrets.token_urlsafe(32)
        hook=GitHubIntake(store,secret,['example/project']);client=TestClient(create_app(store,token,github=hook));auth={'Authorization':'Bearer '+token}
        body=json.dumps({'action':'opened','repository':{'full_name':'example/project'},'issue':{'number':42,'title':'Example issue','body':'Synthetic fixture; not a live repository.'}}).encode()
        headers={'X-Hub-Signature-256':'sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest(),'X-GitHub-Delivery':'demo-42','X-GitHub-Event':'issues'}
        response=client.post('/hooks/github',content=body,headers=headers);assert response.status_code==202,response.text
        ident=response.json()['id'];assert client.post('/hooks/github',content=body,headers=headers).json()['id']==ident
        flows=Workflows(store);worker=Worker(store,default_registry().mapping(),workflows=True)
        for _ in range(2):
            assert not worker.once()  # each step waits for explicit simulated human approval
            wf=flows.get(ident);pending=[s for s in wf['steps'] if s['state']=='waiting_approval'];assert len(pending)==1
            assert client.post('/api/jobs/'+pending[0]['job_id']+'/approve',headers=auth).status_code==200
            assert worker.once()
        assert not worker.once();wf=flows.get(ident);assert wf['state']=='succeeded'
        print(json.dumps({'scenario':'synthetic signed webhook','workflow_state':wf['state'],'steps':[{k:v for k,v in s.items() if k!='job_id'} for s in wf['steps']],'duplicate_deliveries_created':0,'external_writes':0},indent=2))
if __name__=='__main__':main()
