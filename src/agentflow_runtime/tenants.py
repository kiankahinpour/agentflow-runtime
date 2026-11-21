"""Restricted API pilot. Only deterministic built-in adapters, not an OS sandbox."""
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from fastapi import FastAPI
from starlette.responses import JSONResponse
from .api import create_app
from .store import Store
from .plugins import default_registry

SLUG=re.compile(r'[a-z][a-z0-9-]{0,47}\Z')
HEX=re.compile(r'[0-9a-f]{64}\Z')
ROLES={'viewer','submitter','admin'}

def tenant_store(root,slug):
    if not isinstance(slug,str) or not SLUG.fullmatch(slug):raise ValueError('invalid tenant slug')
    root=Path(root).resolve();root.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory=root/slug;directory.mkdir(mode=0o700,exist_ok=True)
    path=directory/'queue.db'
    if directory.is_symlink() or path.is_symlink() or (path.exists() and path.stat().st_nlink!=1):raise ValueError('symlink tenant paths are forbidden')
    return Store(path)

class TenantGate:
    def __init__(self,app,principals,internal):self.app=app;self.principals=principals;self.internal=internal
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        async def deny(status,msg):return await JSONResponse({'detail':msg},status_code=status,headers={'Cache-Control':'no-store'})(scope,receive,send)
        path=scope['path'];root=scope.get('root_path','')
        if root and path.startswith(root+'/'):path=path[len(root):]
        if not path.startswith('/api/') or '//' in path:return await deny(404,'not found')
        auth=[v for k,v in scope['headers'] if k.lower()==b'authorization']
        if len(auth)!=1 or not auth[0].startswith(b'Bearer ') or not 40<=len(auth[0])<=512:return await deny(401,'invalid token')
        digest=hashlib.sha256(auth[0][7:]).hexdigest();role=None
        for expected,r in self.principals:
            if hmac.compare_digest(digest,expected):role=r
        if role is None:return await deny(401,'invalid token')
        if path.startswith('/api/audit') and role!='admin':return await deny(403,'admin required for audit')
        method=scope['method'];read=method=='GET';submit=method=='POST' and path in ('/api/jobs','/api/workflows')
        if not read and not (role=='admin' or role=='submitter' and submit):return await deny(403,'role not permitted')
        # Bound buffered request data for allowed write routes before JSON parsing.
        if method=='POST':
            body=bytearray()
            while True:
                msg=await receive()
                if msg['type']=='http.disconnect':return
                if msg['type']!='http.request':return await deny(400,'invalid request')
                chunk=msg.get('body',b'')
                if len(body)+len(chunk)>1024*1024:return await deny(413,'payload too large')
                body.extend(chunk)
                if not msg.get('more_body',False):break
            original_receive=receive;delivered=False
            async def bounded_receive():
                nonlocal delivered
                if delivered:return await original_receive()
                delivered=True;return {'type':'http.request','body':bytes(body),'more_body':False}
            receive=bounded_receive
        scope=dict(scope);scope['state']={**scope.get('state',{}),'agentflow_actor':'tenant:'+digest[:20]};scope['headers']=[(k,v) for k,v in scope['headers'] if k.lower()!=b'authorization']+[(b'authorization',b'Bearer '+self.internal.encode())]
        return await self.app(scope,receive,send)

def create_tenant_app(root,config):
    if not isinstance(config,dict) or not config or len(config)>64:raise ValueError('1–64 tenants required')
    app=FastAPI(title='AgentFlow restricted tenant API',docs_url=None,redoc_url=None,openapi_url=None)
    all_hashes=set()
    for slug,users in config.items():
        if not isinstance(users,list) or not users or len(users)>100:raise ValueError('1–100 credentials per tenant')
        principals=[]
        for user in users:
            if not isinstance(user,dict) or set(user)!={'sha256','role'} or not isinstance(user['sha256'],str) or not HEX.fullmatch(user['sha256']) or not isinstance(user['role'],str) or user['role'] not in ROLES:raise ValueError('invalid principal')
            if user['sha256'] in all_hashes:raise ValueError('credential reuse forbidden')
            all_hashes.add(user['sha256']);principals.append((user['sha256'],user['role']))
        internal=secrets.token_urlsafe(32);store=tenant_store(root,slug)
        with store.tx() as c:
            if c.execute("SELECT 1 FROM jobs WHERE adapter NOT IN ('echo','word-count') LIMIT 1").fetchone():raise ValueError('tenant DB contains external jobs')
            for row in c.execute('SELECT spec FROM workflows'):
                if any(step['adapter'] not in ('echo','word-count') for step in json.loads(row['spec'])):raise ValueError('tenant DB contains external workflow steps')
        app.mount('/t/'+slug,TenantGate(create_app(store,internal,default_registry(),safe_only=True),principals,internal))
    return app
