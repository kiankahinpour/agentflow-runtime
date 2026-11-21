"""Explicit, trusted adapter registration. No automatic code discovery."""
import importlib
import re
from dataclasses import dataclass
from typing import Callable

NAME = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
PROTOCOL_VERSION = 1

@dataclass(frozen=True)
class AdapterSpec:
    name: str
    execute: Callable
    supports_cancellation: bool = False
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self):
        if not NAME.fullmatch(self.name) or not callable(self.execute):
            raise ValueError('invalid adapter name or callable')
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError('unsupported adapter protocol version')
        if type(self.supports_cancellation) is not bool:
            raise ValueError('supports_cancellation must be boolean')

    def __call__(self, prompt, timeout, *, cancel_event=None):
        if self.supports_cancellation:
            return self.execute(prompt, timeout, cancel_event=cancel_event)
        return self.execute(prompt, timeout)

    def metadata(self):
        return {'name':self.name,'protocol_version':self.protocol_version,
                'supports_cancellation':self.supports_cancellation,
                'approval_required':self.name!='echo','automatic_retry':self.name=='echo'}

class Registry:
    def __init__(self): self._specs={}
    def register(self, spec):
        if not isinstance(spec, AdapterSpec): raise ValueError('expected AdapterSpec')
        if spec.name in self._specs: raise ValueError('duplicate adapter: '+spec.name)
        self._specs[spec.name]=spec
        return self
    def load(self, reference):
        """Import only a reference explicitly supplied by the local operator."""
        module,sep,attribute=reference.partition(':')
        if not sep or not module or not attribute: raise ValueError('plugin must be module:attribute')
        try: spec=getattr(importlib.import_module(module),attribute)
        except (ImportError,AttributeError) as exc: raise ValueError('cannot import plugin: '+reference) from exc
        return self.register(spec)
    def mapping(self): return dict(self._specs)
    def metadata(self): return [s.metadata() for s in self._specs.values()]


def word_count(prompt, timeout):
    """Deterministic offline sample adapter; not an AI model."""
    return str(len(prompt.split()))


def default_registry():
    from .adapters import echo
    return Registry().register(AdapterSpec('echo',echo)).register(AdapterSpec('word-count',word_count))
