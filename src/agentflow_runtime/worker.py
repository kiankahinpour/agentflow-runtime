"""Worker leases, cooperative cancellation and stale-result fencing."""
import math
import threading
import time
import uuid

class ExecutionStopped(Exception):
    """A cooperative adapter confirms it stopped; not proof of rollback."""

class Worker:
    def __init__(self, store, adapters, lease=30, *, workflows=False):
        if not math.isfinite(lease) or lease<0.3: raise ValueError('lease must be at least 0.3 seconds')
        self.store=store; self.adapters=dict(adapters); self.lease=lease
        self.id=uuid.uuid4().hex;self.current_job=None
        self.workflows=workflows

    def once(self):
        if self.workflows:
            from .workflows import Workflows
            Workflows(self.store).tick()
        job=self.store.claim(tuple(self.adapters),self.lease)
        if job is None:return False
        self.current_job=job['id']
        stop=threading.Event(); interrupt=threading.Event()
        def renew():
            # Poll cancellation promptly, even for a long lease.
            while not stop.wait(min(self.lease/3,.25)):
                try:
                    state=self.store.renew(job['id'],job['lease_token'],self.lease)
                    if state is None:
                        interrupt.set(); return
                    if state=='cancel_requested': interrupt.set()
                except Exception:
                    interrupt.set(); return
        thread=threading.Thread(target=renew,daemon=True);thread.start()
        try:
            adapter=self.adapters[job['adapter']]
            try:
                if getattr(adapter,'supports_cancellation',False):
                    result=adapter(job['prompt'],job['timeout'],cancel_event=interrupt)
                else:
                    result=adapter(job['prompt'],job['timeout'])
            except ExecutionStopped:
                self.store.finish(job['id'],job['lease_token'],stopped=True)
            except Exception as exc:
                self.store.finish(job['id'],job['lease_token'],error=f'{type(exc).__name__}: {exc}')
            else:
                self.store.finish(job['id'],job['lease_token'],result=result)
        finally:
            stop.set();thread.join();self.current_job=None
        return True

    def run(self, poll=1):
        stop=threading.Event()
        def report(status=None):
            job=self.current_job
            self.store.worker_status(self.id,self.adapters,status or ('busy' if job else 'idle'),job)
        def monitor():
            while not stop.wait(2):
                try:report()
                except Exception:pass  # telemetry is best effort, not a lease
        report();thread=threading.Thread(target=monitor,daemon=True);thread.start()
        try:
            while True:
                if not self.once():time.sleep(poll)
        finally:
            stop.set();thread.join();report('stopped')
