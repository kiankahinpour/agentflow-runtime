"""Run with AGENTFLOW_AUDIT_HMAC_KEY set; do not commit real keys."""
from pathlib import Path
from agentflow_runtime import Store

store=Store(Path('audit-demo.db'))
store.audit('operator','example','demo-job')
result=store.audit_verify()
print(result)
# Persist result['tip'] separately from your database for later checks.
