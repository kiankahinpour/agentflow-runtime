"""Real Chromium browser smoke test; install playwright and Chromium separately."""
import argparse, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
from agentflow_runtime import Store, Worker
from agentflow_runtime.plugins import default_registry

def main():
    p=argparse.ArgumentParser();p.add_argument('--chromium',default=None);p.add_argument('--offline',action='store_true',help='Render HTML without network; bridge fetch to FastAPI TestClient');p.add_argument('--screenshots',default='browser-artifacts');a=p.parse_args()
    output=Path(a.screenshots);output.mkdir(parents=True,exist_ok=True)
    http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'jobs.db';store=Store(database);token='browser-test-token-not-a-secret-0000'
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        env=os.environ.copy();env['AGENTFLOW_TOKEN']=token
        server=subprocess.Popen([sys.executable,'-m','agentflow_runtime.cli','--db',str(database),'serve','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with http.open(url+'/health',timeout=.2):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('server failed to start')
            with sync_playwright() as pw:
                options={'headless':True};
                if a.chromium:options['executable_path']=a.chromium
                browser=pw.chromium.launch(**options);page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                if a.offline:
                    from fastapi.testclient import TestClient
                    from agentflow_runtime.api import create_app
                    client=TestClient(create_app(store,token))
                    def bridge(path,options):
                        response=client.request(options.get('method','GET'),path,headers=options.get('headers'),content=options.get('body'))
                        return {'status':response.status_code,'body':response.text}
                    page.expose_function('agentflowTestFetch',bridge)
                    page.set_content(client.get('/').text)
                    page.evaluate("""() => { window.fetch=async (path,options)=>{const r=await window.agentflowTestFetch(path,options);return {ok:r.status>=200&&r.status<300,status:r.status,json:async()=>JSON.parse(r.body),text:async()=>r.body}}; }""")
                else:page.goto(url)
                page.locator('#token').fill(token)
                page.get_by_role('button',name='Connect',exact=True).click()
                expect(page.locator('#connection')).to_contain_text('Connected')
                from agentflow_runtime.workflows import Workflows
                workflow_id=Workflows(store).create([{'name':'review','prompt':'Browser workflow','approval':True}],'browser-demo')
                page.get_by_role('button',name='Advance workflows').click()
                expect(page.locator('#flows')).to_contain_text(workflow_id)
                assert Workflows(store).get(workflow_id)['steps'][0]['state']=='waiting_approval'
                store.cancel(Workflows(store).get(workflow_id)['steps'][0]['job_id'])
                Workflows(store).tick()
                page.get_by_role('button',name='Refresh',exact=True).click()
                page.locator('#rows').get_by_text('cancelled',exact=True).wait_for()
                page.locator('#prompt').fill('Browser smoke task');page.locator('#adapter').select_option('word-count');page.get_by_role('button',name='Queue task').click();page.locator('#rows').get_by_text('waiting_approval',exact=True).wait_for()
                page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Approve',exact=True).click();page.locator('#rows').get_by_text('queued',exact=True).wait_for()
                assert Worker(store,default_registry().mapping()).once()
                page.get_by_role('button',name='Refresh',exact=True).click();page.locator('#rows').get_by_text('succeeded',exact=True).wait_for()
                page.get_by_role('row').filter(has_text='Browser smoke task').get_by_role('button',name='View',exact=True).click()
                expect(page.locator('#details')).to_contain_text('"result": "3"')
                store.worker_status('browser-worker',['echo'],'idle')
                page.get_by_role('button',name='Refresh',exact=True).click()
                expect(page.locator('#workers')).to_contain_text('ONLINE')
                expect(page.locator('#feed')).to_contain_text('succeeded')
                expect(page.locator('#audit')).to_contain_text('submit')
                page.locator('#filter').select_option('failed')
                expect(page.locator('#rows tr')).to_have_count(0)
                page.locator('#filter').select_option('succeeded');page.locator('#rows').get_by_text('succeeded',exact=True).wait_for()
                page.locator('#search').fill('no-match')
                expect(page.locator('#rows tr')).to_have_count(0)
                page.locator('#search').fill('Browser smoke');page.locator('#rows').get_by_text('succeeded',exact=True).wait_for()
                for width,height in [(1440,900),(1024,768),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(150)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'horizontal overflow at {width}'
                    page.screenshot(path=str(output/f'dashboard-{width}.png'),full_page=True)
                page.get_by_role('button',name='Disconnect',exact=True).click();assert page.locator('#rows tr').count()==0
                assert not errors,errors;browser.close()
            print(('Offline browser bridge: ' if a.offline else 'Live HTTP: ')+'Browser smoke passed: workflow list and advance, login, adapter choice, submit, approval, worker result, inspection, worker monitor, event feed, filters, search, logout, 3 viewport widths.')
        finally:
            server.terminate();server.wait(timeout=10)
if __name__=='__main__':main()
