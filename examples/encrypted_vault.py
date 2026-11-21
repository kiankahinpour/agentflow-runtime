"""Operator-only example. Provide a real external AGENTFLOW_VAULT_KEY."""
import os
from pathlib import Path
from agentflow_runtime.secrets_vault import EncryptedSecretVault

key=os.environ['AGENTFLOW_VAULT_KEY']
vault=EncryptedSecretVault(Path.home()/'.agentflow_runtime'/'secrets.enc',key)
# Set keys through a secure, local operator UI/secret manager, not hardcoded here.
print('Vault configured. Allowed names:', ['CODEX_API_KEY'])
