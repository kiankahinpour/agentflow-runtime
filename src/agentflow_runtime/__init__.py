"""Durable orchestration for local, trusted agent workloads."""
from ._version import __version__
from .store import Store, Conflict
from .worker import Worker, ExecutionStopped
__all__ = ["Store", "Conflict", "Worker", "ExecutionStopped"]

from .plugins import AdapterSpec, Registry
__all__ += ["AdapterSpec", "Registry"]
