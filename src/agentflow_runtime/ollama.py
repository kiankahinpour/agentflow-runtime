"""Optional local Ollama text-generation adapter; no remote endpoint or auto-download."""
import http.client
import json


def ollama_adapter(model, port=11434):
    if not isinstance(model,str) or not model.strip() or len(model)>200:raise ValueError('invalid Ollama model')
    if type(port) is not int or not 1<=port<=65535:raise ValueError('invalid Ollama port')
    def run(prompt,timeout):
        # Direct loopback connection, no environment proxy and no redirects.
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
        try:
            conn.request('POST','/api/generate',body=json.dumps({'model':model,'prompt':prompt,'stream':False}).encode(),headers={'Content-Type':'application/json'})
            response=conn.getresponse()
            if response.status!=200:raise RuntimeError(f'Ollama HTTP status {response.status}')
            data=response.read(2_000_001)
            if len(data)>2_000_000:raise RuntimeError('Ollama response exceeds 2 MB')
            obj=json.loads(data)
            if not isinstance(obj,dict) or obj.get('done') is not True or not isinstance(obj.get('response'),str):raise RuntimeError('invalid or incomplete Ollama response')
            return obj['response'][:100000]
        finally:conn.close()
    # Socket timeout is not a hard execution deadline or proof the server stopped.
    return run
