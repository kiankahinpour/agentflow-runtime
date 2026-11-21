"""Durable bounded DAGs; dependent jobs are created atomically with their links."""
import json
import re
import time
import uuid
from .store import Conflict

OUTPUT_REF = re.compile(r'\{\{steps\.([a-z][a-z0-9_-]{0,63})\.result\}\}')
STEP = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
TERMINAL = {'failed', 'cancelled', 'uncertain', 'restored_hold'}

def normalize(steps, allowed):
    if not isinstance(steps,list) or not 1 <= len(steps) <= 32:
        raise ValueError('workflow must have 1–32 steps')
    result = {}
    for step in steps:
        if not isinstance(step,dict) or set(step)-{'name','prompt','adapter','depends_on','approval','timeout'}:
            raise ValueError('invalid step fields')
        name=step.get('name'); prompt=step.get('prompt'); adapter=step.get('adapter','echo')
        deps=step.get('depends_on',[]); approval=step.get('approval',False); timeout=step.get('timeout',300)
        if not isinstance(name,str) or not STEP.fullmatch(name) or name in result: raise ValueError('invalid or duplicate step name')
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>100000 or any(0xD800<=ord(ch)<=0xDFFF for ch in prompt): raise ValueError('invalid prompt')
        if not isinstance(adapter,str) or adapter not in allowed: raise ValueError('adapter not allowed')
        if not isinstance(deps,list) or any(not isinstance(d,str) for d in deps) or len(deps)!=len(set(deps)): raise ValueError('invalid dependencies')
        if type(approval) is not bool or type(timeout) is not int or not 1<=timeout<=3600:raise ValueError('invalid approval or timeout')
        result[name]={'name':name,'prompt':prompt,'adapter':adapter,'depends_on':sorted(deps),'approval':approval or adapter!='echo','timeout':timeout}
    for name,step in result.items():
        found=OUTPUT_REF.findall(step['prompt'])
        if any(dep not in step['depends_on'] for dep in found):
            raise ValueError('result reference must target a direct dependency')
        # Fail closed on malformed interpolation, not silently pass template syntax to agents.
        if '{{' in OUTPUT_REF.sub('',step['prompt']) or '}}' in OUTPUT_REF.sub('',step['prompt']):
            raise ValueError('invalid workflow interpolation')
    if sum(len(s['prompt']) for s in result.values())>200000:raise ValueError('workflow prompt budget exceeded')
    seen=set(); visiting=set()
    def visit(n):
        if n in visiting:raise ValueError('dependency cycle')
        if n in seen:return
        if n not in result:raise ValueError('unknown dependency')
        visiting.add(n)
        for d in result[n]['depends_on']:visit(d)
        visiting.remove(n);seen.add(n)
    for n in result:visit(n)
    return json.dumps([result[n] for n in sorted(result)],sort_keys=True,separators=(',',':'))

class Workflows:
    def __init__(self,store):self.store=store
    def create(self,steps,key,allowed=('echo',),*,delivery_digest=None,delivery_id=None):
        if not isinstance(key,str) or not 1<=len(key)<=200 or any(0xD800<=ord(ch)<=0xDFFF for ch in key):raise ValueError('invalid workflow key')
        spec=normalize(steps,allowed)
        with self.store.tx() as c:
            if delivery_digest:
                row=c.execute('SELECT workflow_id FROM github_deliveries WHERE digest=?',(delivery_digest,)).fetchone()
                if row:return row["workflow_id"]
                old_delivery=c.execute('SELECT digest FROM github_deliveries WHERE delivery_id=?',(delivery_id,)).fetchone()
                if old_delivery:raise Conflict('delivery ID already used with a different signed payload')
            old=c.execute('SELECT id,spec FROM workflows WHERE idem=?',(key,)).fetchone()
            if old:
                if old['spec']!=spec:raise Conflict('workflow key already used')
                ident=old['id']
            else:
                ident=uuid.uuid4().hex;now=time.time()
                c.execute('INSERT INTO workflows VALUES(?,?,?,?,?,?)',(ident,key,spec,'active',now,now))
                for step in json.loads(spec):c.execute('INSERT INTO workflow_steps VALUES(?,?,NULL)',(ident,step['name']))
            if delivery_digest:c.execute('INSERT INTO github_deliveries VALUES(?,?,?,?)',(delivery_digest,delivery_id,ident,time.time()))
            return ident
    def get(self,ident):
        from contextlib import closing
        with closing(self.store.connect()) as c:
            row=c.execute('SELECT id,state,created,updated FROM workflows WHERE id=?',(ident,)).fetchone()
            if not row:return None
            out=dict(row);out['steps']=[dict(r) for r in c.execute('SELECT s.name,s.job_id,COALESCE(j.state,\'pending\') AS state FROM workflow_steps s LEFT JOIN jobs j ON j.id=s.job_id WHERE s.workflow_id=? ORDER BY s.name',(ident,))];return out
    def list(self,limit=50):
        from contextlib import closing
        with closing(self.store.connect()) as c:return [dict(r) for r in c.execute('SELECT id,state,created,updated FROM workflows ORDER BY created DESC LIMIT ?',(max(1,min(limit,200)),))]
    def tick(self,limit=100):
        """Transactional coordinator; concurrent ticks cannot enqueue duplicate steps."""
        created=0
        with self.store.tx() as c:
            now=time.time()
            workflows=c.execute("SELECT * FROM workflows WHERE state='active' ORDER BY updated,id LIMIT ?",(max(1,min(limit,100)),)).fetchall()
            for wf in workflows:
                ident=wf['id']; steps=json.loads(wf['spec'])
                states={r['name']:r['state'] for r in c.execute('SELECT s.name,j.state FROM workflow_steps s LEFT JOIN jobs j ON j.id=s.job_id WHERE s.workflow_id=?',(ident,))}
                if any(v in TERMINAL for v in states.values()):state='blocked'
                elif all(v=='succeeded' for v in states.values()):state='succeeded'
                else:
                    state='active'
                    for step in steps:
                        name=step['name']
                        if states[name] is not None or not all(states[d]=='succeeded' for d in step['depends_on']):continue
                        # Only read succeeded direct dependencies, and never interpret
                        # their returned text as a second-stage template.
                        dep_results={}
                        for dep in step['depends_on']:
                            dep_row=c.execute("SELECT j.result FROM workflow_steps s JOIN jobs j ON s.job_id=j.id WHERE s.workflow_id=? AND s.name=? AND j.state='succeeded'",(ident,dep)).fetchone()
                            if dep_row is None:raise RuntimeError('dependency result missing')
                            dep_results[dep]=dep_row['result'] or ''
                        prompt=OUTPUT_REF.sub(lambda match: dep_results[match.group(1)],step['prompt'])
                        if len(prompt)>100000:
                            state='blocked';break
                        job=uuid.uuid4().hex;approval=step['approval']
                        c.execute('INSERT INTO jobs(id,adapter,prompt,state,max_attempts,available,created,updated,timeout) VALUES(?,?,?,?,?,?,?,?,?)',(job,step['adapter'],prompt,'waiting_approval' if approval else 'queued',1,now,now,now,step['timeout']))
                        self.store.event(c,job,'submitted',str(approval));self.store.event(c,job,'workflow_step',ident+':'+name)
                        c.execute('UPDATE workflow_steps SET job_id=? WHERE workflow_id=? AND name=?',(job,ident,name));created+=1
                c.execute('UPDATE workflows SET state=?,updated=? WHERE id=?',(state,now,ident))
        return created
