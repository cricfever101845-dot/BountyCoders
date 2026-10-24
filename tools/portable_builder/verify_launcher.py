"""Bounded check of the shipped launcher, without opening a browser window."""
import hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
from urllib.request import urlopen

def run(root):
    root=Path(root).resolve()
    runtime=root/'runtime/python/python.exe'
    before=hashlib.sha256((root/'app/bountycoders.db').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='bounty_launch_') as folder:
        logpath=Path(folder)/'launcher.log'
        env={**os.environ,'BOUNTY_STATE_DIR':str(Path(folder)/'state'),'PYTHONDONTWRITEBYTECODE':'1',
             'PATH':str(Path(os.environ['SystemRoot'])/'System32')}
        code='import runpy,webbrowser; webbrowser.open=lambda *a,**k: True; runpy.run_path('+repr(str(root/'launcher.py'))+',run_name="__main__")'
        with logpath.open('w') as log:
            proc=subprocess.Popen([str(runtime),'-B','-u','-c',code],stdout=log,stderr=log,env=env)
            try:
                for _ in range(80):
                    text=logpath.read_text(errors='replace')
                    if proc.poll() is not None:raise RuntimeError(text)
                    if 'BountyCoders is ready: ' in text:
                        url=text.split('BountyCoders is ready: ')[1].splitlines()[0].strip()
                        with urlopen(url,timeout=3) as page:assert page.status==200
                        print('PASS: shipped launcher starts bundled server and serves HTTP',flush=True)
                        break
                    time.sleep(.2)
                else:raise RuntimeError('Launcher startup timeout: '+text)
            finally:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
                proc.wait(timeout=5)
    assert hashlib.sha256((root/'app/bountycoders.db').read_bytes()).hexdigest()==before
    reportpath=root/'VERIFICATION_REPORT.json'
    report=json.loads(reportpath.read_text());report['launcher_check']='PASS';report['verified_files']={f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file() and f.name != 'VERIFICATION_REPORT.json' and '__pycache__' not in f.parts};reportpath.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True)
    run(parser.parse_args().release)
