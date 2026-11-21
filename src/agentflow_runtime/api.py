"""Authenticated single-operator API. Bind to loopback by default."""
import secrets
import hashlib
import asyncio
import json
from pathlib import Path
from typing import Optional, Literal
from fastapi import Request, FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from ._version import __version__
from .store import Store, Conflict
from .plugins import default_registry
from .workflows import Workflows
from .github import MAX_BODY

MAX_API_BODY_BYTES = 2 * 1024 * 1024  # Caps JSON before Pydantic validation / DB rate limiting.

class Submission(BaseModel):
    prompt: str = Field(min_length=1,max_length=100000)
    adapter: str=Field(default='echo',min_length=1,max_length=64)
    idem: Optional[str]=Field(default=None,min_length=1,max_length=256)
    max_attempts: int=Field(default=1,ge=1,le=10)
    approval: bool=False
    timeout: int=Field(default=300,ge=1,le=3600)

class Resolution(BaseModel):
    decision: Literal['retry','failed','succeeded','cancelled']
    reason: str=Field(min_length=1,max_length=1000)


def create_app(store: Store, token: str, registry=None, external_catalog=(), *, safe_only=False, github=None, rate_limit_per_minute=600):
    registry=registry if registry is not None else default_registry()
    # Codex remains a known queue target even when its worker is offline.
    catalog={s['name']:s for s in registry.metadata()}
    catalog.setdefault('codex',{'name':'codex','protocol_version':1,'supports_cancellation':True,'approval_required':True,'automatic_retry':False})
    for name in external_catalog:
        if name not in ('claude','opencode','sandbox','vm'):raise ValueError('unknown external catalog adapter')
        catalog.setdefault(name,{'name':name,'protocol_version':1,'supports_cancellation':True,'approval_required':True,'automatic_retry':False})
    if safe_only: catalog={k:v for k,v in catalog.items() if k in ('echo','word-count')}
    flows=Workflows(store)
    if len(token)<24:raise ValueError('API token must be at least 24 characters')
    app=FastAPI(title='AgentFlow Runtime',version=__version__,docs_url=None,redoc_url=None,openapi_url=None)
    if type(rate_limit_per_minute) is not int or not 1<=rate_limit_per_minute<=100000:
        raise ValueError('invalid rate limit')
    def auth(request:Request, authorization: Optional[str]=Header(default=None)):
        if not secrets.compare_digest((authorization or '').encode(),('Bearer '+token).encode()):
            raise HTTPException(401,'invalid token',headers={'WWW-Authenticate':'Bearer'})
        actor=request.scope.get('state',{}).get('agentflow_actor') if safe_only else None
        actor=actor or 'api:'+hashlib.sha256(token.encode()).hexdigest()[:20]
        allowed,retry=store.rate_limit(actor,rate_limit_per_minute)
        if not allowed:raise HTTPException(429,'rate limit exceeded',headers={'Retry-After':str(retry)})
        request.state.actor=actor
    @app.middleware('http')
    async def headers(request, call_next):
        # FastAPI parses JSON bodies *before* evaluating auth dependencies. Avoid
        # accepting or parsing arbitrarily large anonymous API requests. This is
        # a per-request memory bound, not an IP-wide denial-of-service defense.
        response = None
        if request.url.path.startswith('/api/') and request.method in ('POST', 'PUT', 'PATCH'):
            supplied = (request.headers.get('authorization') or '').encode()
            expected = ('Bearer ' + token).encode()
            if not secrets.compare_digest(supplied, expected):
                response = PlainTextResponse('invalid token', status_code=401,
                                             headers={'WWW-Authenticate': 'Bearer'})
            else:
                length = request.headers.get('content-length')
                if length is not None:
                    try:
                        parsed_length = int(length)
                    except ValueError:
                        parsed_length = -1
                    if parsed_length < 0:
                        response = PlainTextResponse('invalid content-length', status_code=400)
                    elif parsed_length > MAX_API_BODY_BYTES:
                        response = PlainTextResponse('request body too large', status_code=413)
                if response is None:
                    body = bytearray()
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > MAX_API_BODY_BYTES:
                            response = PlainTextResponse('request body too large', status_code=413)
                            break
                        body.extend(chunk)
                    if response is None:
                        # Starlette reuses Request.body() cached by this middleware.
                        request._body = bytes(body)
        if response is None:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        return response
    @app.get('/health')
    def health():return {'status':'ok'}
    @app.get('/health/ready')
    def ready():
        try:store.statistics()
        except Exception as exc:raise HTTPException(503,'database unavailable') from exc
        return {'status':'ready'}
    @app.get('/',response_class=HTMLResponse)
    def dashboard():
        return Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8').replace(
            '{{runtime_version}}', __version__)
    @app.get('/api/runtime',dependencies=[Depends(auth)])
    def runtime():
        backend='postgresql' if store.__class__.__name__=='PostgresStore' else 'sqlite'
        return {'version':__version__,'backend':backend,'distributed_coordination':backend=='postgresql',
                'hostile_multi_tenant_execution':False}
    @app.get('/api/audit',dependencies=[Depends(auth)])
    def audit(limit:int=Query(100,ge=1,le=500)):return store.audit_records(limit)
    @app.get('/api/audit/verify',dependencies=[Depends(auth)])
    def verify_audit(expected_tip:Optional[str]=None):return store.audit_verify(expected_tip)
    @app.get('/api/metrics',dependencies=[Depends(auth)],response_class=PlainTextResponse)
    def metrics():
        from .metrics import render_metrics
        return PlainTextResponse(render_metrics(store),media_type='text/plain; version=0.0.4; charset=utf-8')
    @app.get('/api/jobs',dependencies=[Depends(auth)])
    def jobs(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),state:Optional[str]=None):return store.list(limit,state=state,offset=offset)
    @app.get('/api/adapters',dependencies=[Depends(auth)])
    def adapters():return list(catalog.values())
    @app.get('/api/stats',dependencies=[Depends(auth)])
    def stats():return store.statistics()
    @app.get('/api/workers',dependencies=[Depends(auth)])
    def workers():return store.workers()
    @app.get('/api/events',dependencies=[Depends(auth)])
    def global_events(after:Optional[int]=Query(None,ge=0),limit:int=Query(100,ge=1,le=500)):
        return store.global_events(limit,after=after)
    @app.get('/api/events/stream',dependencies=[Depends(auth)])
    async def stream(request:Request,after:int=Query(0,ge=0),seconds:int=Query(15,ge=1,le=30)):
        async def generate():
            cursor=after;deadline=asyncio.get_running_loop().time()+seconds
            while not await request.is_disconnected() and asyncio.get_running_loop().time()<deadline:
                rows=await run_in_threadpool(lambda:store.global_events(100,after=cursor))
                for row in rows:
                    cursor=row['seq'];yield f'id: {cursor}\ndata: {json.dumps(row)}\n\n'
                if not rows:yield ': heartbeat\n\n';await asyncio.sleep(.5)
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    @app.post('/api/recover',dependencies=[Depends(auth)])
    def recover(request:Request):
        n=store.recover_expired();store.audit(request.state.actor,'recover','queue','ok');return {'recovered':n}
    @app.get('/api/jobs/{ident}',dependencies=[Depends(auth)])
    def job(ident:str):
        j=store.get(ident)
        if j is None:raise HTTPException(404,'job not found')
        return j
    @app.get('/api/jobs/{ident}/events',dependencies=[Depends(auth)])
    def events(ident:str,limit:int=Query(200,ge=1,le=500),after:Optional[int]=Query(None,ge=0)):
        job(ident);return store.events(ident,limit,after=after)
    @app.post('/api/jobs/{ident}/resolve',dependencies=[Depends(auth)])
    def resolve(ident:str, resolution:Resolution, request:Request):
        job(ident)
        try:state=store.resolve(ident,resolution.decision,resolution.reason)
        except Conflict as e:raise HTTPException(409,str(e)) from e
        except ValueError as e:raise HTTPException(422,str(e)) from e
        store.audit(request.state.actor,'resolve_'+resolution.decision,ident,'ok');return {'id':ident,'state':state}
    @app.post('/api/jobs',dependencies=[Depends(auth)],status_code=201)
    def submit(sub:Submission, request:Request):
        try:
            if sub.adapter not in catalog:raise ValueError('unknown adapter')
            # All non-echo API submissions require explicit human approval.
            ident=store.submit(sub.prompt,sub.adapter,idem=sub.idem,max_attempts=sub.max_attempts,approval=sub.approval or sub.adapter!='echo',timeout=sub.timeout)
        except Conflict as e:raise HTTPException(409,str(e)) from e
        except ValueError as e:raise HTTPException(422,str(e)) from e
        store.audit(request.state.actor,'submit',ident,'ok');return {'id':ident}
    @app.post('/api/jobs/{ident}/approve',dependencies=[Depends(auth)])
    def approve(ident:str, request:Request):
        job(ident)
        try:store.approve(ident)
        except Conflict as e:raise HTTPException(409,str(e)) from e
        store.audit(request.state.actor,'approve',ident,'ok');return {'id':ident,'state':'queued'}
    @app.post('/api/jobs/{ident}/cancel',dependencies=[Depends(auth)])
    def cancel(ident:str, request:Request):
        job(ident)
        try:state=store.cancel(ident)
        except Conflict as e:raise HTTPException(409,str(e)) from e
        store.audit(request.state.actor,'cancel',ident,'ok');return {'id':ident,'state':state}
    @app.post('/api/workflows',dependencies=[Depends(auth)],status_code=201)
    def create_workflow(payload:dict, request:Request):
        try:
            if set(payload)!={'key','steps'}:raise ValueError('key and steps required')
            ident=flows.create(payload['steps'],payload['key'],catalog);store.audit(request.state.actor,'workflow_create',ident,'ok');return {'id':ident}
        except ValueError as e:raise HTTPException(422,str(e)) from e
        except Conflict as e:raise HTTPException(409,str(e)) from e
    @app.get('/api/workflows',dependencies=[Depends(auth)])
    def workflows(limit:int=Query(50,ge=1,le=200)):return flows.list(limit)
    @app.get('/api/workflows/{ident}',dependencies=[Depends(auth)])
    def workflow(ident:str):
        result=flows.get(ident)
        if result is None:raise HTTPException(404,'workflow not found')
        return result
    @app.post('/api/workflow-tick',dependencies=[Depends(auth)])
    def tick(request:Request):
        created=flows.tick();store.audit(request.state.actor,'workflow_tick','scheduler','ok');return {'created':created}
    if github is not None and not safe_only:
        @app.post('/hooks/github',status_code=202)
        async def github_hook(request:Request):
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>MAX_BODY:raise HTTPException(413,'payload too large')
                body.extend(chunk)
            if not github.authenticated(body,request.headers.get('x-hub-signature-256','')):raise HTTPException(401,'invalid signature')
            try:
                ident=await run_in_threadpool(github.ingest,body,request.headers.get('x-github-event',''),request.headers.get('x-github-delivery',''))
            except ValueError as e:raise HTTPException(422,str(e)) from e
            except PermissionError as e:raise HTTPException(403,str(e)) from e
            except Conflict as e:raise HTTPException(409,str(e)) from e
            return {'id':ident,'accepted':ident is not None}
    return app
