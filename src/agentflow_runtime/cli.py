import argparse
import json
import os
import sqlite3
from .store import Store, Conflict

def _open_store(db):
    if os.environ.get("AGENTFLOW_POSTGRES_DSN"):
        from .postgres import PostgresStore
        return PostgresStore(os.environ['AGENTFLOW_POSTGRES_DSN'],pool_size=int(os.environ.get('AGENTFLOW_PG_POOL_SIZE','0')))
    return Store(db)

from .worker import Worker
from .adapters import codex_adapter
from .ollama import ollama_adapter
from .external import cli_adapter
from .plugins import default_registry, AdapterSpec, NAME

def main():
    p=argparse.ArgumentParser(prog='agentflow');p.add_argument('--db',default=os.environ.get('AGENTFLOW_DB','agentflow.db'))
    s=p.add_subparsers(dest='cmd',required=True)
    q=s.add_parser('submit');q.add_argument('prompt');q.add_argument('--adapter',default='echo');q.add_argument('--key');q.add_argument('--approve',action='store_true');q.add_argument('--attempts',type=int,default=1);q.add_argument('--timeout',type=int,default=300)
    w=s.add_parser('worker');w.add_argument('--once',action='store_true');w.add_argument('--codex-workspace');w.add_argument('--claude-workspace');w.add_argument('--opencode-workspace');w.add_argument('--ollama-model');w.add_argument('--ollama-port',type=int,default=11434);w.add_argument('--plugin',action='append',default=[])
    for name in ['get','approve','cancel','events']:
        s.add_parser(name).add_argument('id')
    ls=s.add_parser('list');ls.add_argument('--state');ls.add_argument('--limit',type=int,default=50);ls.add_argument('--offset',type=int,default=0)
    s.add_parser('stats');s.add_parser('recover')
    av=s.add_parser('audit-verify');av.add_argument('--expected-tip')
    b=s.add_parser('backup');b.add_argument('destination')
    restore=s.add_parser('restore');restore.add_argument('snapshot')
    r=s.add_parser('resolve');r.add_argument('id');r.add_argument('decision',choices=['retry','failed','succeeded','cancelled']);r.add_argument('--reason',required=True)
    server=s.add_parser('serve');server.add_argument('--port',type=int,default=8787);server.add_argument('--enable-claude',action='store_true');server.add_argument('--enable-opencode',action='store_true');server.add_argument('--ollama-model');server.add_argument('--ollama-port',type=int,default=11434);server.add_argument('--plugin',action='append',default=[])
    wf=s.add_parser('workflow');wf.add_argument('spec');wf.add_argument('--key',required=True);wf.add_argument('--allow-adapter',action='append',default=[])
    s.add_parser('workflow-tick');wg=s.add_parser('workflow-get');wg.add_argument('id')
    w.add_argument('--workflows',action='store_true')
    w.add_argument('--sandbox-image',help='digest-pinned, locally available Docker image; no network')
    w.add_argument('--sandbox-command',nargs='+',help='argv inside sandbox; provide after other worker options')
    w.add_argument('--sandbox-cpus',type=float,default=1.0)
    w.add_argument('--sandbox-memory',type=int,default=256)
    w.add_argument('--vm-image',help='operator-provisioned QEMU qcow2 guest image')
    w.add_argument('--vm-sha256',help='SHA256 of the pinned guest image')
    w.add_argument('--vm-memory',type=int,default=256)
    w.add_argument('--vm-cores',type=int,default=1)
    w.add_argument('--vm-require-ready',action='store_true',default=True,help='require guest AGENTFLOW_READY marker before sending prompt (default and required for supported images)')
    server.add_argument('--enable-sandbox',action='store_true',help='expose sandbox queue target; worker must have Docker adapter')
    server.add_argument('--enable-vm',action='store_true',help='expose vm queue target; worker must have VM adapter')
    server.add_argument('--rate-limit',type=int,default=600,help='authenticated requests per actor per minute')
    server.add_argument('--github-repo',action='append',default=[]);server.add_argument('--github-adapter',default='echo',choices=['echo','codex','claude','opencode'])
    ts=s.add_parser('tenant-serve');ts.add_argument('--root',required=True);ts.add_argument('--config',required=True);ts.add_argument('--port',type=int,default=8787)
    tw=s.add_parser('tenant-worker');tw.add_argument('--root',required=True);tw.add_argument('--tenant',required=True);tw.add_argument('--once',action='store_true')
    a=p.parse_args()
    try:
        if a.cmd=='restore':
            if os.environ.get('AGENTFLOW_POSTGRES_DSN'):
                raise RuntimeError('PostgreSQL restore requires pg_restore on a dedicated halted database')
            print(Store.restore(a.snapshot,a.db).path);return
        if a.cmd=='tenant-serve':
            import uvicorn
            from .tenants import create_tenant_app
            from pathlib import Path
            uvicorn.run(create_tenant_app(a.root,json.loads(Path(a.config).read_text())),host='127.0.0.1',port=a.port,access_log=False);return
        if a.cmd=='tenant-worker':
            from .tenants import tenant_store
            store=tenant_store(a.root,a.tenant)
            worker=Worker(store,default_registry().mapping(),workflows=True)
            if a.once:worker.once()
            else:worker.run()
            return
        store=_open_store(a.db)
        if a.cmd=='submit':
            if not NAME.fullmatch(a.adapter):raise ValueError('invalid adapter name')
            print(store.submit(a.prompt,a.adapter,idem=a.key,approval=a.approve or a.adapter!='echo',max_attempts=a.attempts,timeout=a.timeout))
        elif a.cmd in ('workflow','workflow-tick','workflow-get'):
            from .workflows import Workflows
            from pathlib import Path
            flows=Workflows(store)
            if a.cmd=='workflow':print(flows.create(json.loads(Path(a.spec).read_text()),a.key,['echo','word-count',*a.allow_adapter]))
            elif a.cmd=='workflow-tick':print(flows.tick())
            else:print(json.dumps(flows.get(a.id),indent=2))
        elif a.cmd=='serve':
            try:
                import uvicorn
                from .api import create_app
            except ImportError as exc:raise RuntimeError('install agentflow-durable[server]') from exc
            token=os.environ.get('AGENTFLOW_TOKEN','')
            registry=default_registry()
            if a.ollama_model:registry.register(AdapterSpec('ollama',ollama_adapter(a.ollama_model,a.ollama_port)))
            for ref in a.plugin:registry.load(ref)
            github=None
            if a.github_repo:
                from .github import GitHubIntake
                github=GitHubIntake(store,os.environ.get('AGENTFLOW_GITHUB_SECRET',''),a.github_repo,a.github_adapter)
            uvicorn.run(create_app(store,token,registry,external_catalog=[n for n in ('claude','opencode','sandbox','vm') if getattr(a,'enable_'+n)],github=github,rate_limit_per_minute=a.rate_limit),host='0.0.0.0' if os.environ.get('AGENTFLOW_CONTAINER_BIND')=='1' else '127.0.0.1',port=a.port,access_log=False)
        elif a.cmd=='worker':
            registry=default_registry()
            if a.codex_workspace:registry.register(AdapterSpec('codex',codex_adapter(a.codex_workspace),True))
            for name in ('claude','opencode'):
                workspace=getattr(a,name+'_workspace')
                if workspace:registry.register(AdapterSpec(name,cli_adapter(name,workspace),True))
            if a.ollama_model:registry.register(AdapterSpec('ollama',ollama_adapter(a.ollama_model,a.ollama_port)))
            for ref in a.plugin:registry.load(ref)
            if a.sandbox_image:
                if not a.sandbox_command:raise ValueError('--sandbox-command required with --sandbox-image')
                from .sandbox import DockerSandboxAdapter
                registry.register(AdapterSpec('sandbox',DockerSandboxAdapter(a.sandbox_image,a.sandbox_command,cpus=a.sandbox_cpus,memory_mb=a.sandbox_memory),True))
            elif a.sandbox_command:
                raise ValueError('--sandbox-command requires --sandbox-image')
            if a.vm_image:
                if not a.vm_sha256:raise ValueError('--vm-sha256 required with --vm-image')
                from .vm import QemuVMAdapter
                registry.register(AdapterSpec('vm',QemuVMAdapter(a.vm_image,a.vm_sha256,ram_mb=a.vm_memory,cores=a.vm_cores,require_ready=a.vm_require_ready),True))
            elif a.vm_sha256:raise ValueError('--vm-sha256 requires --vm-image')
            worker=Worker(store,registry.mapping(),workflows=a.workflows)
            if a.once:worker.once()
            else:worker.run()
        elif a.cmd=='cancel':print(store.cancel(a.id))
        elif a.cmd=='approve':store.approve(a.id)
        elif a.cmd=='resolve':print(store.resolve(a.id,a.decision,a.reason))
        elif a.cmd=='backup':print(store.backup(a.destination))
        elif a.cmd=='recover':print(store.recover_expired())
        elif a.cmd=='audit-verify':print(json.dumps(store.audit_verify(a.expected_tip),indent=2))
        elif a.cmd=='stats':print(json.dumps(store.statistics(),indent=2))
        elif a.cmd=='list':print(json.dumps(store.list(a.limit,state=a.state,offset=a.offset),indent=2,ensure_ascii=False))
        else: print(json.dumps(getattr(store,a.cmd)(a.id),indent=2,ensure_ascii=False))
    except (Conflict,ValueError,RuntimeError,OSError,sqlite3.Error) as e:p.exit(2,f'error: {e}\n')
    except KeyboardInterrupt:pass

if __name__=='__main__':main()
