"""Trusted local example: PYTHONPATH=examples agentflow worker --plugin custom_plugin:PLUGIN."""
from agentflow_runtime import AdapterSpec

def uppercase(prompt, timeout):
    return prompt.upper()

PLUGIN = AdapterSpec('uppercase', uppercase)
