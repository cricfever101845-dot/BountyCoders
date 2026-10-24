"""Offline integration verification. All test accounts/progress use a temporary DB."""
from __future__ import annotations
import argparse, hashlib, http.cookiejar, json, os, secrets, socket, sqlite3
import subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser
from contextlib import closing

checks = []
def check(ok, message):
    if not ok: raise RuntimeError(message)
    checks.append(message)
    print('OK: ' + message, flush=True)

def source(language, expected):
    if language.lower().startswith('python'): return 'print(' + repr(expected) + ', end="")'
    literal = json.dumps(expected, ensure_ascii=True)
    if language.lower().startswith('java'):
        return 'public class Main { public static void main(String[] a) { System.out.print(' + literal + '); }}'
    if language.lower().startswith('c'):
        return '#include <stdio.h>\nint main(void) { printf("%s", ' + literal + '); return 0; }'
    # A structural fixture, covering every rule expressed by the existing bank.
    return '''<h2>Title</h2><h3>Welcome</h3><h4>Title</h4><p>Text</p><b>Bold</b><i>Italic</i>
    <a href="https://google.com"><img src="sample.png" alt="demo" width="200" height="200"></a>
    <img src="second.png" alt="two"><br><hr><!-- comment -->
    <ul><li>One</li></ul><ol><li>One</li></ol><textarea>Text</textarea>
    <form><input type="email" required><input type="password"><input type="checkbox">
    <input type="number"><input type="radio"><input type="date"><input type="color"><input type="reset">
    <button>submit</button><select><option>One</option></select></form>
    <table><caption>Title</caption><tr><th>Heading</th><td>Cell</td></tr></table>
    <iframe title="demo"></iframe><audio controls></audio><video controls></video>
    <header><nav>Nav</nav></header><section>Section</section><main>Main</main><footer>Footer</footer>'''

class Assets(HTMLParser):
    def __init__(self): super().__init__(); self.paths = set()
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src','href') and value and value.startswith('/static/'):
                self.paths.add(value)

def run(root):
    root = root.resolve(); (root/'VERIFICATION_REPORT.json').unlink(missing_ok=True); appdir = root/'app'; runtime = root/'runtime/python/python.exe'
    check(os.name == 'nt', 'Windows execution host')
    for path in (runtime, root/'tools/tcc/tcc.exe', root/'tools/jdk/bin/javac.exe', appdir/'bountycoders.db'):
        check(path.is_file(), 'Included ' + str(path.relative_to(root)))
    before = hashlib.sha256((appdir/'bountycoders.db').read_bytes()).hexdigest()
    sys.path.insert(0,str(appdir))
    import flask, bounty_runner
    from evaluator import compare_outputs
    from html_evaluator import evaluate_html
    os.environ['BC_RUNNER_MODE']='portable'
    # Remove development PATH and Java settings; all tools must resolve from the release.
    os.environ['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
    for key in ('JAVA_HOME','JDK_HOME','PYTHONPATH','PYTHONHOME','CC','CXX'):
        os.environ.pop(key,None)
    languages = ['Python','Java','C language']
    failures = {
        'Python': ['if True print(5)', 'raise RuntimeError("test")', 'while True: pass'],
        'Java': ['public class Main { broken }', 'public class Main { public static void main(String[] a){throw new RuntimeException("test");}}', 'public class Main { public static void main(String[] a){while(true){}}}'],
        'C language': ['int main(void){ broken syntax }', '#include <stdlib.h>\nint main(void){exit(3);}', 'int main(void){for(;;){}return 0;}']}
    for lang in languages:
        result=bounty_runner.run_student_code(source(lang,'5'),lang,None)
        check(not result['error'] and result['output']=='5',lang+' success with development PATH removed')
        check(not compare_outputs('wrong','5',mode='normalized').is_correct,lang+' wrong output rejected')
        for code,typ in zip(failures[lang],['compilation_error','runtime_error','timeout']):
            t=time.monotonic(); result=bounty_runner.run_student_code(code,lang,None)
            check(result['error_type']==typ and time.monotonic()-t<40,lang+' '+typ+' bounded feedback')
    html=source('html and css','')
    check(bounty_runner.run_student_code(html,'html and css',None)['output']==html,'HTML/CSS runner')
    check(evaluate_html(html,'<form> and <input and <button>').is_correct,'HTML structure accepted')
    check(not evaluate_html('<!-- <form><input><button> -->','<form> and <input and <button>').is_correct,'HTML comment spoof rejected')
    with closing(sqlite3.connect(appdir/'bountycoders.db')) as db:
        db.row_factory=sqlite3.Row
        courses=[dict(x) for x in db.execute('select * from courses')]
        questions=[dict(x) for x in db.execute('select * from questions')]
        check(db.execute('select count(*) from users').fetchone()[0]==0,'Release has no personal accounts')
        for q in questions:
            if 'html' in q['language'].lower():
                for alt in (1,2,3):
                    check(evaluate_html(html,q[f'expected_output_{alt}']).is_correct,f'HTML bank {q["level"]}/{q["question_number"]} variant {alt}')
    with tempfile.TemporaryDirectory(prefix='bounty_verify_') as temp:
        work=Path(temp)
        with closing(sqlite3.connect(appdir/'bountycoders.db')) as src, closing(sqlite3.connect(work/'bountycoders.db')) as dst: src.backup(dst)
        with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env={**os.environ,'BOUNTY_PORT':str(port),'BOUNTY_SECRET_KEY':secrets.token_hex(32),'PYTHONDONTWRITEBYTECODE':'1'}
        opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def request(path, data=None, form=False):
            from urllib.parse import urlencode, quote
            body=(urlencode(data).encode() if form else json.dumps(data).encode()) if data is not None else None
            req=Request(base+quote(path,safe='/:?=&%'),data=body,headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'})
            try:
                with opener.open(req,timeout=45) as response: return response.status,response.read(65536) if path.startswith("/static/") else response.read()
            except HTTPError as exc: return exc.code,exc.read()
        def api(path,data=None):
            status,body=request(path,data)
            return status,json.loads(body)
        with (work/'server.log').open('w') as log:
            server=subprocess.Popen([str(runtime),'-B',str(appdir/'app.py')],cwd=work,env=env,stdout=log,stderr=log)
            try:
                for _ in range(80):
                    if server.poll() is not None: raise RuntimeError((work/'server.log').read_text())
                    try:
                        if request('/start')[0]==200: break
                    except (URLError,OSError): pass
                    time.sleep(.2)
                else: raise RuntimeError('HTTP startup timeout')
                check(True,'Flask HTTP startup using bundled Python')
                check(api('/api/start_session',{'course_id':'101'})[0]==401,'Anonymous game request rejected')
                status,body=request('/signup',{'username':'portable_test','email':'portable@example.invalid','password':'DemoPass123','confirm_password':'DemoPass123'},True)
                check(status==200 and b'BOUNTY' in body,'Signup and authenticated home page')
                assets=set()
                for page in ['/','/login','/signup','/home','/course_select']+[f'/game/{c["id"]}' for c in courses]:
                    status,body=request(page);check(status==200,'Page loads '+page)
                    parser=Assets();parser.feed(body.decode());assets.update(parser.paths)
                for asset in sorted(assets):check(request(asset)[0]==200,'Asset loads '+asset)
                # Every bundled static file must also be served (includes CSS/video/font).
                for file in (appdir/'static').rglob('*'):
                    if file.is_file() and file.suffix.lower() not in ('.pyc','.bak'):
                        status,_=request('/static/'+file.relative_to(appdir/'static').as_posix())
                        check(status==200,'Static file '+file.name)
                for course in courses:
                    cid=course['id'];status,data=api('/api/start_session',{'course_id':cid})
                    check(status==200 and not data.get('error'),'Start '+course['name'])
                    check('expected_output' not in json.dumps(data),'Answers hidden from client')
                    check(api('/api/complete_course',{'course_id':cid})[0]==409,'Premature completion rejected '+cid)
                    first=data['session_questions']['easy'][0]
                    wrong={'course_id':cid,'level':'easy','question_number':1,'code':'<div>Wrong</div>' if cid=='103' else source(course['language'],'definitely wrong')}
                    status,out=api('/api/submit_answer',wrong)
                    check(status==200 and out.get('error_type')=='wrong_output','API wrong answer '+cid)
                    resumed=api('/api/start_session',{'course_id':cid})[1]
                    check(resumed['current_question_number']==1 and resumed['bounty_earned']==0,'Wrong answer preserves progress '+cid)
                    rotated=api('/api/get_questions',{'course_id':cid,'level':'easy','question_number':1})[1]
                    check(rotated['question']['alt']!=first['alt'],'Question rotation '+cid)
                    data=api('/api/start_session',{'course_id':cid})[1]
                    for level in ('easy','medium','hard'):
                        for number,q in enumerate(data['session_questions'][level],1):
                            row=next(x for x in questions if x['id']==q['id'])
                            payload={'course_id':cid,'level':level,'question_number':number,'code':source(row['language'],row[f'expected_output_{q["alt"]}'])}
                            status,out=api('/api/submit_answer',payload)
                            check(status==200 and out.get('correct') is True,f'Grading/progression {cid} {level}/{number}: {out}')
                            check(api('/api/submit_answer',payload)[0]==409,'Duplicate answer rejected')
                    check(out['completed'] and api('/api/complete_course',{'course_id':cid})[1].get('completed'),'Course completes '+cid)
                    check(request('/completion/'+cid)[0]==200,'Completion page '+cid)
                with closing(sqlite3.connect(work/'bountycoders.db')) as db:
                    check(db.execute('select total_bounty from users where username=?',('portable_test',)).fetchone()[0]==600000000,'Total bounty correct across 60 questions')
                    check(db.execute('select count(*) from bounty_records').fetchone()[0]==4,'Four completed course records')
                check(api('/api/course_history')[0]==200,'Course history API')
                request('/logout')
                status,_=request('/login',{'email':'portable_test','password':'DemoPass123'},True)
                check(status==200,'Existing account login')
            finally:
                server.terminate()
                try: server.wait(timeout=5)
                except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)
    check(hashlib.sha256((appdir/'bountycoders.db').read_bytes()).hexdigest()==before,'Release database unchanged by verification')
    report={'status':'PASS','checks':len(checks),'root':str(root),'tests':checks,'limitations':['Windows 10/11 x64 only','Trusted local code only; execution is not sandboxed','HTML/CSS validation is structural; no browser pixel comparison','Generated answer fixtures verify execution/grading contracts, not pedagogical solution quality']}
    (root/'VERIFICATION_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'PASS: {len(checks)} checks',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,default=Path(__file__).resolve().parent);args=parser.parse_args()
    try: run(args.release)
    except Exception as exc:
        print('FAILED:',exc,file=sys.stderr);sys.exit(1)
