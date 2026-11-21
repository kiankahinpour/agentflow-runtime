#!/usr/bin/env python3
"""Tiny *deterministic* reference guest. No shell, arbitrary code, or network.

Input: one newline-terminated JSON object with a UTF-8 prompt.
Output: a READY marker then exactly one base64 result line over ttyS0.
Extend only after a guest threat-model/security review.
"""
import base64
import json
import sys

MAX_LINE=100_100

def process(raw):
    if len(raw)>MAX_LINE:raise ValueError('request size limit')
    request=json.loads(raw)
    if not isinstance(request,dict) or set(request)!={'prompt'}:raise ValueError('invalid schema')
    prompt=request['prompt']
    if not isinstance(prompt,str) or not 0<len(prompt)<=100000:raise ValueError('invalid prompt')
    return prompt

def main():
    print('AGENTFLOW_READY',flush=True)
    try:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        result=process(line)
        print('AGENTFLOW_RESULT='+base64.b64encode(result.encode('utf-8')).decode('ascii'),flush=True)
    except Exception:
        print('AGENTFLOW_ERROR=invalid_request',flush=True)
        raise SystemExit(1)
if __name__=='__main__':main()
