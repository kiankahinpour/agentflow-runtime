"""PyInstaller entrypoint; packages the same trusted local-only desktop."""
# Explicit imports aid frozen dependency discovery (dynamic CLI commands).
import agentflow_runtime.api  # noqa: F401
import agentflow_runtime.cli  # noqa: F401
import agentflow_runtime.adapters  # noqa: F401
import agentflow_runtime.store  # noqa: F401
from agentflow_runtime.desktop import main

if __name__ == '__main__':
    raise SystemExit(main())
