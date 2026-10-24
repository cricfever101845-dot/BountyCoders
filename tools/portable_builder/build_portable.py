"""One-time build of an offline, portable BountyCoders Windows x64 college demo.

Runs on the developer's Windows PC with Python and pip installed. Produces a
self-contained release folder + ZIP. On target PCs, no Python, Docker, Java,
or C compiler installation is needed. Target: Windows 10/11 x64 only.

Offline portability necessarily bundles Python, a Temurin JDK and TinyCC C
compiler. Their archives are large. Internet is needed ONLY at build time.

IMPORTANT: This is a local, TRUSTED DEMO; code is not sandboxed. It must not
be run on public/LAN interfaces or with untrusted student code.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

SELF = Path(__file__).resolve().parent
RELEASE_NAME = 'BountyCoders_Submission_Windows_x64'
PYTHON_VERSION = '3.13.17'
PYTHON_MINOR = '313'
PYTHON_URL = 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip'
JAVA_URL = 'https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse'
FONT_URL = 'https://raw.githubusercontent.com/google/fonts/main/ofl/tradewinds/TradeWinds-Regular.ttf'
FONT_LICENSE_URL = 'https://raw.githubusercontent.com/google/fonts/main/ofl/tradewinds/OFL.txt'
PYPI = ['Flask==3.1.2', 'blinker==1.9.0', 'click==8.5.0', 'itsdangerous==2.2.0', 'Jinja2==3.1.6', 'MarkupSafe==3.0.4', 'Werkzeug==3.1.9']  # dependencies resolved into Win64 CPython 3.13 wheels
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache',
               'node_modules', '.vscode', '.idea', 'dist', 'build', '_bounty_upgrade_backups',
               '.compiler_cache', 'demo_data', 'tools'}


def announce(msg):
    print('\n' + '=' * 64 + '\n' + msg + '\n' + '=' * 64, flush=True)


def choose_project(s):
    if s:
        return Path(s.strip('"')).expanduser().resolve()
    for root in (Path.cwd(), SELF):
        if (root / 'app.py').is_file():
            return root
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk(); r.withdraw()
        chosen = filedialog.askdirectory(title='Choose your BountyCoders folder (contains app.py)')
        r.destroy()
        if chosen:
            return Path(chosen).resolve()
    except Exception:
        pass
    value = input('Paste the complete folder path containing app.py: ').strip('" ')
    if not value:
        raise RuntimeError('No BountyCoders project selected.')
    return Path(value).expanduser().resolve()


def verify_download(path, name=None):
    import hashlib, json
    lock = SELF / 'download_checksums.json'
    expected = json.loads(lock.read_text(encoding='utf-8')).get(name or path.name) if lock.exists() else None
    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Cached/downloaded file checksum mismatch: ' + str(path))


def download(url, output):
    """Use cached verified archives when already present. HTTPS downloads with progress."""
    min_bytes = 100 if output.suffix.lower() == '.txt' else (1_000 if output.suffix.lower() == '.ttf' else 10_000)
    if output.is_file() and output.stat().st_size > min_bytes:
        verify_download(output)
        print('  Cached:', output.name)
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + '.part')
    print('  Downloading:', output.name, '\n   ', url, flush=True)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'BountyCodersCollegeReleaseBuilder/1.0',
        'Accept': '*/*',
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as response, tmp.open('wb') as file:
            content_type = response.headers.get('Content-Type','')
            length = int(response.headers.get('Content-Length') or 0)
            if 'text/html' in content_type.lower():
                raise RuntimeError('Received an HTML page instead of the expected downloadable file.')
            n = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                file.write(block); n += len(block)
                if n % (16 * 1024 * 1024) < len(block):
                    label = f'{n/1048576:.0f} MiB'
                    if length:
                        label += f' of {length/1048576:.0f} MiB'
                    print('   ',label,flush=True)
        if n < min_bytes:
            raise RuntimeError('Downloaded file is unexpectedly small.')
        verify_download(tmp, output.name)
        os.replace(tmp, output)
        print(f'  Saved {n / 1048576:.1f} MiB')
        return output
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def zip_extract_safe(archive, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        # Explicit path traversal defense for downloaded archives.
        for entry in z.infolist():
            p = Path(entry.filename.replace('\\', '/'))
            if p.is_absolute() or '..' in p.parts or re.match(r'^[A-Za-z]:', entry.filename):
                raise RuntimeError('Archive contains an unsafe file path: ' + entry.filename)
        z.extractall(dest)


def flatten_nested_directory(folder, executable):
    if (folder / executable).is_file():
        return
    matches = list(folder.rglob(executable))
    if len(matches) != 1:
        raise RuntimeError(f'Expected one {executable} in {folder}; found {len(matches)}.')
    nested = matches[0].parents[len(Path(executable).parts)-1]
    if nested.resolve() == folder.resolve():
        return
    temp = folder.with_name(folder.name + '_flatten_' + uuid.uuid4().hex[:6])
    shutil.move(str(nested), str(temp))
    shutil.rmtree(folder)
    shutil.move(str(temp), str(folder))


def copy_folder_contents(src, dst):
    for item in src.iterdir():
        if item.name in IGNORE_DIRS or item.name.lower().startswith('bountycoders_submission_'):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store',
                                               '.git', '.venv', 'node_modules', '.compiler_cache'))
        elif item.is_file() and item.suffix.lower() not in ('.zip', '.bak', '.log', '.db-wal', '.db-shm'):
            shutil.copy2(item, dst / item.name)


def patch_flask_app(app_file):
    code = app_file.read_text(encoding='utf-8-sig')
    # Secret key is generated by launcher and persisted locally; not the public hardcoded key.
    secret_re = re.compile(r'(?m)^app\.secret_key\s*=\s*[^\n]+$')
    code, n = secret_re.subn("app.secret_key = os.environ.get('BOUNTY_SECRET_KEY') or os.urandom(32)", code, count=1)
    if n != 1:
        raise RuntimeError('Could not replace app.secret_key safely; app.py structure changed.')
    run_re = re.compile(r'(?m)^([ \t]*)app\.run\([^\n]*\)\s*$')
    code, n = run_re.subn(lambda m: m.group(1) + "app.run(host='127.0.0.1', port=int(os.environ.get('BOUNTY_PORT', '5000')), debug=False, use_reloader=False)", code, count=1)
    if n != 1:
        raise RuntimeError('Could not replace app.run safely; app.py structure changed.')
    compile(code, 'app.py', 'exec')
    app_file.write_text(code, encoding='utf-8')


def clean_database(src_db, target_db):
    source = sqlite3.connect(src_db.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    target = sqlite3.connect(str(target_db))
    try:
        source.backup(target)
        tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'questions', 'courses'}.issubset(tables):
            raise RuntimeError('Existing database is missing questions/courses tables. Cannot build demo.')
        q_count = target.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        course_count = target.execute('SELECT COUNT(*) FROM courses').fetchone()[0]
        if q_count < 15 or course_count < 1:
            raise RuntimeError(f'Question bank incomplete: {q_count} questions, {course_count} courses.')
        target.execute('PRAGMA foreign_keys=OFF')
        for private_table in ('users', 'progress', 'bounty_records', 'user_profiles', 'question_rotation'):
            if private_table in tables:
                target.execute('DELETE FROM "' + private_table + '"')
        if 'sqlite_sequence' in tables:
            for tbl in ('users', 'progress', 'bounty_records'):
                target.execute('DELETE FROM sqlite_sequence WHERE name=?', (tbl,))
        target.commit()
        print(f'  Included {q_count} question groups and {course_count} courses.')
        print('  Removed personal user accounts, course progress and bounty history from submission copy.')
    finally:
        target.close(); source.close()


def patch_question_engine(target_app):
    """Apply the earlier question engine only to the STAGED copy, never to the dev folder."""
    import upgrade_question_engine as upgrader
    for name in ('bounty_engine.py', 'bounty_runner.py'):
        shutil.copy2(SELF / name, target_app / name)
    app_file = target_app / 'app.py'
    home_file = target_app / 'templates' / 'home.html'
    game_file = target_app / 'templates' / 'game.html'
    for p in (app_file, home_file, game_file):
        if not p.is_file():
            raise FileNotFoundError(f'Expected project file missing: {p}')
    app_code = upgrader.patch_app(app_file.read_text(encoding='utf-8-sig'))
    home = upgrader.replace_marked_css(home_file.read_text(encoding='utf-8-sig'),
                                     'bounty-history-layout-v2', upgrader.HISTORY_CSS)
    game = upgrader.patch_game(game_file.read_text(encoding='utf-8-sig'))
    for path, data in ((app_file, app_code), (home_file, home), (game_file, game)):
        path.write_text(data, encoding='utf-8')
    patch_flask_app(app_file)
    print('  Upgraded rotating questions, answer checking, and side-by-side Course History.')


def add_offline_styles(target_app, font_file, license_file):
    css_folder = target_app / 'static' / 'css'
    fonts_folder = target_app / 'static' / 'fonts'
    css_folder.mkdir(parents=True, exist_ok=True)
    fonts_folder.mkdir(parents=True, exist_ok=True)
    if font_file and font_file.exists():
        shutil.copy2(font_file, fonts_folder / 'TradeWinds-Regular.ttf')
        if license_file and license_file.exists():
            shutil.copy2(license_file, fonts_folder / 'OFL-Trade-Winds.txt')
    # If the local project has not yet been updated, enforce the requested split home title.
    home_file = target_app / 'templates' / 'home.html'
    if home_file.is_file():
        current = home_file.read_text(encoding='utf-8-sig')
        if 'bc-title-split' not in current and 'hero-title-wrap' not in current:
            current, altered = re.subn(r'<h1\s+id=[\"\']title[\"\']\s*>\s*BOUNTY\s+CODERS\s*</h1>',
                '<h1 id="title" class="bc-release-title"><span>BOUNTY</span><span class="bc-ship-gap" aria-hidden="true"></span><span>CODERS</span></h1>',
                current, count=1, flags=re.I)
            if altered:
                home_file.write_text(current, encoding='utf-8')
                print('  Split the home title around the ship in the video.')
    stylesheet = '''/* Local font; no Google Fonts request needed during the demo. */
@font-face {font-family:'Trade Winds'; src:url('/static/fonts/TradeWinds-Regular.ttf') format('truetype'); font-style:normal; font-weight:400; font-display:swap;}
/* Pirate font across pages; code editors retain monospace readability. */
html, body, body * {font-family:'Trade Winds','Trebuchet MS',Arial,sans-serif!important;}
#code-editor,#result-display,#lost-error-msg,code,pre,kbd,samp {
  font-family:Consolas,'Courier New',monospace!important;
}
/* Normal bold home title: blue letters, gold/yellow border, center ship gap. */
#title.bc-release-title {
  width:min(1250px,96vw)!important;max-width:none!important;display:grid!important;
  grid-template-columns:minmax(0,1fr) clamp(170px,30vw,440px) minmax(0,1fr)!important;
  align-items:center!important;position:relative!important;top:0!important;left:auto!important;
  padding:0!important;margin:0 auto 26px!important;background:transparent!important;
  text-shadow:none!important;-webkit-text-stroke:0 transparent!important;
}
#title.bc-release-title span:not(.bc-ship-gap) {
  font-family:Arial,Helvetica,sans-serif!important;font-weight:900!important;
  color:#1174ed!important;-webkit-text-stroke:2.5px #ffd43b!important;
  paint-order:stroke fill;font-size:clamp(25px,4.2vw,65px)!important;
  line-height:1.1!important;white-space:nowrap!important;text-align:center!important;
  text-shadow:0 2px 9px rgba(0,16,40,.28)!important;
}
body:has(.bc-release-title) #play-btn {
  position:static!important;left:auto!important;margin:0 auto!important;
}
@media(max-width:670px) {
 #title.bc-release-title {grid-template-columns:minmax(0,1fr) 18vw minmax(0,1fr)!important;}
 #title.bc-release-title span:not(.bc-ship-gap) {-webkit-text-stroke:1.5px #ffd43b!important;font-size:clamp(17px,4.3vw,30px)!important;}
}
/* Preserve the game's existing styles; fix known course history overlap. */
#history-modal #history-content .history-item {display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;flex-wrap:wrap!important;}
#history-modal .history-item .course-name {position:static!important;float:none!important;flex:1 1 140px!important;width:auto!important;min-width:0!important;transform:none!important;text-shadow:none!important;-webkit-text-stroke:0!important;}
#history-modal .history-item .course-meta {position:static!important;float:none!important;flex:0 1 auto!important;width:auto!important;transform:none!important;}
/* Keep the ship video vivid, as requested. */
#bg-video,#quiz-bg-video,#intro-video,#transition-video {filter:none!important; opacity:1!important;}
body:has(#bg-video)::before {content:none!important;background:none!important;opacity:0!important;}
'''
    (css_folder / 'bounty_submission.css').write_text(stylesheet, encoding='utf-8')
    tag = '<link rel="stylesheet" href="/static/css/bounty_submission.css" data-bounty-submission="1">'
    count = 0
    for html in (target_app / 'templates').glob('*.html'):
        code = html.read_text(encoding='utf-8-sig')
        if '</head>' not in code.lower():
            continue  # empty placeholder templates
        code = re.sub(r'<link[^>]*data-bounty-submission="1"[^>]*>\s*', '', code, flags=re.I)
        code = re.sub(r'</head\s*>', tag + '\n</head>', code, count=1, flags=re.I)
        html.write_text(code, encoding='utf-8')
        count += 1
    for path in list((target_app / 'templates').glob('*.html')) + list(css_folder.glob('*.css')):
        text = path.read_text(encoding='utf-8-sig')
        text = re.sub(r'<link[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', text)
        text = re.sub(r"@import\s+url\(['\"]https://fonts\.googleapis\.com[^;]+;", '', text)
        path.write_text(text, encoding='utf-8')
    print(f'  Linked offline-friendly styling in {count} HTML pages.')


def vendor_wheels(cache, python_home):
    wheel_cache = cache / 'wheels_py313_win_amd64'
    wheel_cache.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
           '--only-binary=:all:', '--platform', 'win_amd64', '--python-version', '3.13',
           '--implementation', 'cp', '--abi', 'cp313', '--dest', str(wheel_cache)] + PYPI
    print('  Resolving Flask + dependencies for portable CPython 3.13...')
    required = {item.split('==')[0].lower() for item in PYPI}
    cached = {wheel.name.split('-')[0].lower() for wheel in wheel_cache.glob('*.whl')}
    if not required.issubset(cached):
        subprocess.run(cmd, check=True, timeout=180)
    else:
        print('  Reusing complete cached Flask dependency wheels.')
    wheels = list(wheel_cache.glob('*.whl'))
    if len(wheels) < 5:
        raise RuntimeError('pip did not download all of Flask’s dependencies.')
    libs = python_home / 'Lib' / 'site-packages'
    libs.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        verify_download(wheel)
        with zipfile.ZipFile(wheel) as z:
            for item in z.infolist():
                if item.is_dir():
                    continue
                p = Path(item.filename)
                if p.is_absolute() or '..' in p.parts:
                    raise RuntimeError('Unsafe wheel path: ' + item.filename)
                # PEP 427: .data/{purelib,platlib} installed to site-packages.
                if len(p.parts) >= 3 and p.parts[0].endswith('.data'):
                    if p.parts[1] in ('purelib', 'platlib'):
                        p = Path(*p.parts[2:])
                    else:
                        continue
                dst = libs.joinpath(*p.parts)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as inp, dst.open('wb') as out:
                    shutil.copyfileobj(inp, out)
    print(f'  Vendored {len(wheels)} dependency wheels; no pip on exam PCs.')


def setup_runtimes(cache, folder):
    runtime = folder / 'runtime' / 'python'
    tools = folder / 'tools'
    runtime.mkdir(parents=True, exist_ok=True)
    tools.mkdir(parents=True, exist_ok=True)
    announce('1/4 Downloading portable Python runtime')
    zip_extract_safe(download(PYTHON_URL, cache / 'python-3.13.17-embed-amd64.zip'), runtime)
    pathfile = runtime / 'python313._pth'
    if not pathfile.exists() or not (runtime / 'python.exe').is_file():
        raise RuntimeError('Portable Python archive is incomplete.')
    pathfile.write_text('python313.zip\n.\nLib\\site-packages\n..\\..\\app\nimport site\n', encoding='ascii')
    vendor_wheels(cache, runtime)
    if os.name == 'nt':
        result = subprocess.run([str(runtime / 'python.exe'), '-c',
                  'import flask, markupsafe, jinja2, werkzeug; print("Portable Flask OK")'],
                  cwd=folder, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Bundled Python could not import Flask: ' + result.stderr)

    announce('2/4 Downloading portable Java JDK (required for offline Java course)')
    jdk = tools / 'jdk'
    zip_extract_safe(download(JAVA_URL, cache / 'temurin-jdk-21-win64.zip'), jdk)
    flatten_nested_directory(jdk, 'bin/javac.exe')
    for exe in ('bin/javac.exe', 'bin/java.exe'):
        if not (jdk / exe).is_file():
            raise RuntimeError('Java executable missing: ' + exe)

    announce('3/4 Preparing portable TinyCC C compiler')
    tcc = tools / 'tcc'
    archive = download('https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27-win64-bin.zip',
                       cache / 'tcc-0.9.27-win64-bin.zip')
    import hashlib
    if hashlib.sha256(archive.read_bytes()).hexdigest() != '34a721949a2583fdff725312da092fa0f5f1f284b702e6f811c6954714faabb2':
        raise RuntimeError('TinyCC archive checksum mismatch')
    zip_extract_safe(archive, tools)
    source_archive = download('https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27.tar.bz2',
                              cache / 'tcc-0.9.27.tar.bz2')
    import tarfile
    license_dir = folder / 'licenses' / 'tinycc'
    license_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_archive, license_dir / source_archive.name)
    with tarfile.open(source_archive) as tar:
        member = next(item for item in tar.getmembers() if item.name.endswith('/COPYING'))
        (license_dir / 'COPYING').write_bytes(tar.extractfile(member).read())
    if not (tcc / 'tcc.exe').is_file():
        raise RuntimeError('Portable TinyCC compiler missing')

    if os.name == 'nt':
        # Ensure compiler executables are valid on the *development PC*.
        print('  Checking bundled Java and C tools...', flush=True)
        for cmd in ((jdk / 'bin/java.exe', '-version'), (jdk / 'bin/javac.exe', '-version'),
                    (tcc / 'tcc.exe', '-v')):
            p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, timeout=40)
            if p.returncode:
                raise RuntimeError('Toolchain check failed: ' + str(cmd[0]) + '\n' + p.stderr)
    print('  Portable Python, Java and C compiler are included in the release.')


def build_zip(folder, output):
    import json
    report = folder / 'VERIFICATION_REPORT.json'
    if not report.is_file() or json.loads(report.read_text(encoding='utf-8')).get('status') != 'PASS':
        raise RuntimeError('Refusing to ZIP an unverified release')
    import hashlib
    verified = json.loads(report.read_text(encoding='utf-8'))
    if verified.get('launcher_check') != 'PASS':
        raise RuntimeError('Launcher has not passed verification')
    for relative, digest in verified.get('verified_files', {}).items():
        if hashlib.sha256((folder / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Release changed after verification: ' + relative)
    archive = output / (RELEASE_NAME + '.zip')
    temporary = archive.with_suffix('.zip.part')
    print('  Compressing release ZIP (video/toolchain files can be large)...', flush=True)
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=1,
                         allowZip64=True) as z:
        for f in sorted(folder.rglob('*')):
            if f.is_file() and not any(part in f.parts for part in ('.compiler_cache','__pycache__')) and not any(token in f.name for token in ('.before-', '.backup-', '.bak')):
                z.write(f, arcname=str(Path(RELEASE_NAME) / f.relative_to(folder)))
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:
            raise RuntimeError('ZIP integrity test failed')
    os.replace(temporary, archive)
    return archive


def prepare_project(project, release):
    srcdb = project / 'bountycoders.db'
    # A clean Git clone can build from the versioned question bank without a personal DB.
    dest = release / 'app'
    dest.mkdir(parents=True, exist_ok=True)
    # All app source, templates and local videos/images copied from local project.
    required = ('app.py', 'evaluator.py', 'html_evaluator.py', 'templates', 'static')
    for name in required:
        if not (project / name).exists():
            raise FileNotFoundError(f'Project missing {name}. Select the correct folder.')
    for file in ('app.py','evaluator.py','html_evaluator.py'):
        shutil.copy2(project / file, dest / file)
    for dirname in ('templates', 'static'):
        (dest / dirname).mkdir(exist_ok=True)
        copy_folder_contents(project / dirname, dest / dirname)
    print('  Copied project assets, HTML templates, Python source, videos and images.')
    if srcdb.is_file():
        clean_database(srcdb, dest / 'bountycoders.db')
    else:
        from create_demo_database import create_database
        create_database(dest / 'bountycoders.db')
    patch_question_engine(dest)
    shutil.copy2(SELF / 'launcher.py', release / 'launcher.py')
    shutil.copy2(SELF / 'START_BOUNTYCODERS.bat', release / 'START_BOUNTYCODERS.bat')
    shutil.copy2(SELF / 'VERIFY_SUBMISSION.bat', release / 'VERIFY_SUBMISSION.bat')
    shutil.copy2(SELF / 'verify_release.py', release / 'verify_release.py')
    shutil.copy2(SELF / 'verify_launcher.py', release / 'verify_launcher.py')
    (dest / 'demo_data').mkdir(exist_ok=True)


def write_readme(release):
    txt = '''BOUNTY CODERS — FINAL COLLEGE SUBMISSION (PORTABLE WIN64)
=========================================================

HOW TO LAUNCH ON AN EXAMINER'S COMPUTER:
  1. Unzip the COMPLETE folder onto a Windows 10/11 x64 PC.
  2. Double-click START_BOUNTYCODERS.bat (inside this folder).
  3. Your default browser opens BountyCoders. Create a demo account.
  4. Keep the console window open while using the site; Ctrl+C stops it.

NO INSTALLATION on the examiner's computer:
  - Python + Flask/Jinja2 are bundled.
  - Java JDK (Temurin 21) is bundled.
  - C compiler (TinyCC 0.9.27) is bundled.
  - Quiz questions, database, music, video and images are bundled.
  - The application runs OFFLINE on 127.0.0.1 only (localhost).

RESTRICTIONS:
  - WINDOWS 10/11 x64 only. Not macOS, Linux, Android or 32-bit Windows.
  - This package is NOT a sandbox. Programs written in the code editor
    run locally with the signed-in Windows user's permissions. ONLY
    run trusted demonstration code. Do not expose the server to LAN/Internet
    or let untrusted people type arbitrary code on the examiner's PC.
  - Some antivirus tools may scan new executable/compiler files.
  - Your release contains a CLEAN database with questions/courses but NO
    original user accounts/passwords or past progress. Create a demo login.
  - Do not run database reset scripts inside the released folder.
  - The built-in browser needs JavaScript and video support (Edge/Chrome).
  - If your existing page contains external assets, those may require internet;
    the default included project assets and Trade Winds font are local.

TECHNOLOGY / LICENSING:
  Python (PSF): https://www.python.org/psf/license/
  Flask and dependencies: https://palletsprojects.com/
  Eclipse Temurin 21 (GPLv2 + Classpath Exception): https://adoptium.net/
  TinyCC 0.9.27 (LGPL 2.1): https://bellard.org/tcc/
  Trade Winds font (SIL OFL): https://github.com/google/fonts/tree/main/ofl/tradewinds
  Respect the terms for all third-party images/videos in the project.

This package is a local college-demo distribution, not a hosted service.
The compiled runtime is prepared on the development Windows PC first.
'''
    (release / 'README_FIRST.txt').write_text(txt, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description='Build an OFFLINE Windows x64 BountyCoders submission.')
    ap.add_argument('--project', help='Folder containing your current BountyCoders app.py')
    ap.add_argument('--output', help='Destination for release folder/ZIP; defaults to project parent')
    ap.add_argument('--cache', help='Folder for cached download ZIPs (reuses previous downloads)')
    ap.add_argument('--prepare-only', action='store_true',
                    help='Test staging/patching without downloading Win64 runtimes (NOT portable).')
    args = ap.parse_args()
    if not args.prepare_only and os.name != 'nt':
        raise RuntimeError('Build the full portable Windows release on a Windows 10/11 x64 developer PC.')
    project = choose_project(args.project)
    if not (project / 'app.py').is_file():
        raise FileNotFoundError(f'Not a BountyCoders project folder: {project}')
    output = Path(args.output).expanduser().resolve() if args.output else project / 'dist'
    output.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache).expanduser().resolve() if args.cache else Path(os.environ.get('LOCALAPPDATA', str(SELF))) / 'BountyCodersBuilds' / 'download_cache'
    release = output / RELEASE_NAME
    if release.exists():
        raise FileExistsError(f'Existing release folder detected: {release}\nRename/move it before building to avoid deleting work.')
    stage = output / ('.' + RELEASE_NAME + '.building.' + uuid.uuid4().hex[:8])
    announce('BountyCoders: building a fresh college submission from ' + str(project))
    print('The existing development project will NOT be modified.')
    try:
        stage.mkdir(parents=True, exist_ok=False)
        prepare_project(project, stage)
        announce('4/4 Adding offline fonts and finishing release' if not args.prepare_only else 'Preparing staged project for tests')
        font = None; license_file = None
        if not args.prepare_only:
            setup_runtimes(cache, stage)
            try:
                font = download(FONT_URL, cache / 'TradeWinds-Regular.ttf')
                license_file = download(FONT_LICENSE_URL, cache / 'TradeWinds-OFL.txt')
            except Exception as exc:
                print('  WARNING: Could not include optional offline Trade Winds font:', exc)
                print('  The UI will use fallback fonts when there is no internet.')
        add_offline_styles(stage / 'app', font, license_file)
        write_readme(stage)
        stage.rename(release)
        if args.prepare_only:
            print('\nPREPARE-ONLY SUCCESS: staged sources created; WITHOUT runtimes. NOT portable:', release)
            return 0
        announce('Final verification: Python + Java + C + Flask localhost')
        verify = subprocess.run([str(release / 'runtime' / 'python' / 'python.exe'),
                                 '-B', str(release / 'verify_release.py')],
                                cwd=release, timeout=600)
        if verify.returncode != 0:
            raise RuntimeError('Runtime smoke test FAILED. Package not ready for submission.\n'
                               'See errors above or run VERIFY_SUBMISSION.bat in the release folder.')
        launch_check = subprocess.run([str(release / 'runtime/python/python.exe'), '-B',
            str(release / 'verify_launcher.py'), '--release', str(release)], cwd=release, timeout=40)
        if launch_check.returncode:
            raise RuntimeError('Shipped launcher verification failed; no ZIP created')
        cache_dir = release / '.compiler_cache'
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        archive = build_zip(release, output)
        announce('SUCCESS! COMPLETE OFFLINE SUBMISSION IS READY')
        print('Folder:', release)
        print('ZIP:', archive)
        print('\nOn another Windows 10/11 x64 PC: unzip full folder and double-click START_BOUNTYCODERS.bat')
        print('No Python/Java/GCC/Docker installation is necessary on that PC.')
        return 0
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if release.exists():
            print('A release folder was created but could not be verified: ' + str(release))
            print('Do NOT submit the release unless VERIFY_SUBMISSION.bat passes.')
        raise


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        print('\nBUILD FAILED:', e, file=sys.stderr)
        print('Your original BountyCoders project is unchanged.', file=sys.stderr)
        print('Check your network/cache or send me the complete error message.', file=sys.stderr)
        raise SystemExit(1)
