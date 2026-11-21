from pathlib import Path
from tempfile import TemporaryDirectory
from agentflow_runtime import Store, Worker
from agentflow_runtime.adapters import echo

with TemporaryDirectory() as directory:
    store=Store(Path(directory)/'demo.db')
    job=store.submit('Hello from AgentFlow!',idem='demo',approval=True)
    store.approve(job)
    Worker(store,{'echo':echo}).once()
    print(store.get(job))
    print(store.events(job))
