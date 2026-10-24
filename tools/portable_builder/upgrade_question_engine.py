#!/usr/bin/env python3
"""BountyCoders: safe one-click History UI + 3-question rotation + grading upgrade.

Usage (PowerShell): py install_bountycoders_upgrade.py
Or: py install_bountycoders_upgrade.py "C:\\path\\to\\BountyCoders"
"""
import base64
import datetime
import os
import re
import shutil
import sqlite3
import sys
import zlib
from pathlib import Path

# Data for engine and runner are embedded below by the build step.
EMBEDDED_FILES = {'bounty_engine.py': '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', 'bounty_runner.py': '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'}
MARKER_BEGIN = '# BEGIN BOUNTY_ENGINE_V2'
MARKER_END = '# END BOUNTY_ENGINE_V2'

HISTORY_CSS = r'''/* BEGIN BOUNTY_HISTORY_LAYOUT_V2 */
#history-modal .modal-inner {
  display: block !important;
  width: min(540px, 94vw) !important;
  min-width: 0 !important;
  max-width: 540px !important;
  max-height: min(80vh, 700px) !important;
  overflow-y: auto !important;
  background: linear-gradient(160deg, rgba(17,44,69,.98), rgba(4,20,34,.98)) !important;
  border: 1px solid rgba(255,203,78,.55) !important;
  border-radius: 22px !important;
  box-shadow: 0 20px 65px rgba(0,0,0,.62) !important;
  padding: 30px !important;
  color: #f7f9ff !important;
}
#history-modal .modal-title {
  display:block !important;
  position: static !important;
  margin: 4px 28px 22px !important;
  font-family: 'Trade Winds', cursive !important;
  color: #ffd15d !important;
  text-align: center !important;
  font-size: clamp(18px, 3vw, 24px) !important;
  line-height:1.4 !important;
  text-shadow: none !important;
}
#history-modal .tab-bar {display:flex !important; gap:12px !important; margin:0 0 18px !important;}
#history-modal .tab-btn {
  min-width:0 !important;
  color: #e5effe !important;
  border: 1px solid rgba(255,209,93,.35) !important;
  background: rgba(255,255,255,.1) !important;
  font-family: 'Trade Winds', cursive !important;
  font-size: 14px !important;
  line-height: 1.4 !important;
  padding: 12px 7px !important;
  text-shadow: none !important;
}
#history-modal .tab-btn.active {
  color: #0b2340 !important;
  background: #ffd15d !important;
  border-color: #ffd15d !important;
}
#history-modal #history-content {
  min-height: 80px !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 10px !important;
  align-items: stretch !important;
  position:static !important;
  overflow: visible !important;
}
#history-modal #history-content .history-item {
  position:relative !important;
  display:flex !important;
  flex-direction:row !important;
  align-items:center !important;
  justify-content:space-between !important;
  flex-wrap:wrap !important;
  gap:10px 16px !important;
  width:100% !important;
  height:auto !important;
  min-height:66px !important;
  margin:0 !important;
  padding:13px 16px !important;
  background:rgba(255,255,255,.075) !important;
  border:1px solid rgba(196,221,249,.18) !important;
  border-radius:12px !important;
  box-sizing:border-box !important;
  overflow:hidden !important;
}
#history-modal #history-content .history-item .course-name,
#history-modal #history-content .history-item .course-meta {
  display:block !important;
  position:static !important;
  float:none !important;
  flex:none !important;
  width:100% !important;
  height:auto !important;
  min-height:0 !important;
  padding:0 !important;
  margin:0 !important;
  inset:auto !important;
  transform:none !important;
  rotate:none !important;
  filter:none !important;
  -webkit-text-stroke:0 !important;
  text-shadow:none !important;
  text-transform:none !important;
  letter-spacing:.01em !important;
  line-height:1.45 !important;
  text-align:left !important;
  white-space:normal !important;
  overflow-wrap:anywhere !important;
  box-shadow:none !important;
  background:transparent !important;
  border:0 !important;
}
#history-modal #history-content .history-item .course-name {
  color:#ffe3a3 !important;
  flex:1 1 155px !important;
  width:auto !important;
  font-family:'Segoe UI',Arial,sans-serif !important;
  font-size:16px !important;
  font-weight:750 !important;
}
#history-modal #history-content .history-item .course-meta {
  color:#c8d5e6 !important;
  flex:0 1 auto !important;
  width:auto !important;
  text-align:right !important;
  font-family:'Segoe UI',Arial,sans-serif !important;
  font-size:13px !important;
  font-weight:500 !important;
  opacity:1 !important;
}
#history-modal .modal-close {color:#fff !important;}
@media (max-width:480px) {
  #history-modal .modal-inner {padding:22px 16px !important;}
  #history-modal #history-content .history-item .course-meta {text-align:left !important;}
}
/* END BOUNTY_HISTORY_LAYOUT_V2 */'''

GAME_CSS = r'''/* BEGIN BOUNTY_GAME_FEEDBACK_V2 */
#result-display {max-height: 190px; overflow-y: auto; overflow-wrap:anywhere;}
#quiz-panel #code-editor {font-family:Consolas,'Courier New',monospace !important;}
/* END BOUNTY_GAME_FEEDBACK_V2 */'''

ROTATE_JS = r'''async function rotateQuestion() {
    const out = document.getElementById('result-display');
    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    try {
      const resp = await fetch('/api/get_questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          course_id: GAME_CONFIG.courseId,
          level: currentStage,
          question_number: currentLevelIndex + 1
        })
      });
      const data = await resp.json();
      if (!resp.ok || !data.question) {
        throw new Error(data.error || 'Unable to load another question.');
      }
      if (!sessionQuestions[currentStage]) sessionQuestions[currentStage] = [];
      sessionQuestions[currentStage][currentLevelIndex] = data.question;
      document.getElementById('question-text').textContent = data.question.question_text;
      document.getElementById('code-editor').value = '';
      if (out) out.style.display = 'none';
    } catch (err) {
      showResult('Could not get a new question: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  }
  '''


def replace_marked_css(html, mark, css):
    pat = re.compile(r'<style\s+id="'+re.escape(mark)+r'">[\s\S]*?</style>', re.I)
    html = pat.sub('', html)
    if not re.search(r'</head\s*>', html, re.I):
        raise ValueError('HTML file has no </head> tag')
    return re.sub(r'</head\s*>', '<style id="'+mark+'">\n'+css+'\n</style>\n</head>', html, count=1, flags=re.I)


def patch_game(html):
    html = replace_marked_css(html, 'bounty-game-feedback-v2', GAME_CSS)
    if 'function rotateQuestion()' not in html or 'function updateHeartsDisplay()' not in html:
        raise ValueError('Cannot find game rotation functions; game.html may have changed')
    a = html.index('function rotateQuestion()')
    b = html.index('function updateHeartsDisplay()', a)
    html = html[:a] + ROTATE_JS + html[b:]
    # The server obtains expected_output and language from its database now.
    html = re.sub(r"^\s*expected_output:\s*q\s*\?\s*q\.expected_output\s*:\s*'',\s*\n", '', html, flags=re.M)
    html = re.sub(r"^\s*language:\s*q\s*\?\s*q\.language\s*:\s*GAME_CONFIG\.courseLanguage\s*\n", '', html, flags=re.M)
    # Insert HTTP validation once inside submitAnswer (not all fetch handlers).
    start = html.index('async function submitAnswer()')
    end = html.index('async function continueToNextLeg()', start)
    block = html[start:end]
    guard = """const data = await resp.json();
      if (!resp.ok) {
        showResult('⚠️ ' + (data.error || 'Could not check your answer.'), 'error');
        btn.disabled = false;
        return;
      }"""
    if "Could not check your answer." not in block:
        block, count = re.subn(r'const data = await resp\.json\(\);',lambda m:guard,block,count=1)
        if count != 1:
            raise ValueError('Could not find answer response handler')
    block = block.replace("showResult('✅ Correct! Great job, Captain!', 'success');",
        "showResult('✅ ' + (data.success_message || 'Correct! Next island unlocked!') + "
        "(data.output ? '\\nOutput:\\n' + data.output : ''), 'success');")
    # Missing Docker/JDK is a server configuration problem, not a wrong answer.
    if "Runner not ready:" not in block:
        block, count = re.subn(r'\} else \{\s*hearts--;',
          lambda m: '''} else {
        if (data.error_type === 'configuration_error' || data.error_type === 'unsupported_language') {
          showResult('⚙️ Runner not ready: ' + (data.error || 'Check server configuration.'), 'error');
          btn.disabled = false;
          return;
        }
        hearts--;''', block, count=1)
        if count != 1:
            raise ValueError('Could not find incorrect-answer handler')
    html = html[:start] + block + html[end:]
    return html


def patch_app(text):
    if MARKER_BEGIN in text:
        pattern = re.compile(re.escape(MARKER_BEGIN)+r'[\s\S]*?'+re.escape(MARKER_END))
        text = pattern.sub('', text)
    code = '''# BEGIN BOUNTY_ENGINE_V2
import bounty_engine
bounty_engine.install(app, get_db, run_code, compare_outputs, classify_error, evaluate_html)
# END BOUNTY_ENGINE_V2

'''
    match = re.search(r'(?m)^if __name__\s*==\s*[\'\"]__main__[\'\"]\s*:', text)
    if not match:
        raise ValueError('Cannot find the app.py entry point')
    return text[:match.start()] + code + text[match.start():]


def locate_root():
    if len(sys.argv) > 1 and sys.argv[1] not in ('--help', '-h'):
        return Path(sys.argv[1].strip('"')).expanduser().resolve()
    for candidate in (Path.cwd(), Path(__file__).resolve().parent):
        if (candidate / 'app.py').is_file() and (candidate / 'templates' / 'home.html').is_file():
            return candidate
    try:
        import tkinter as tk
        from tkinter import filedialog
        app = tk.Tk()
        app.withdraw()
        folder = filedialog.askdirectory(title='Select your BountyCoders project folder (contains app.py)')
        app.destroy()
        if folder:
            return Path(folder).resolve()
    except Exception:
        pass
    folder = input('Enter BountyCoders project folder path: ').strip().strip('"')
    if not folder:
        raise ValueError('No project folder was chosen')
    return Path(folder).expanduser().resolve()


def main():
    print('BountyCoders Upgrade - History UI + Rotating Questions + Answer Checking')
    root = locate_root()
    for rel in ('app.py', 'templates/home.html', 'templates/game.html'):
        if not (root / rel).is_file():
            raise FileNotFoundError('Not a valid BountyCoders folder: missing ' + rel)
    contents = {}
    for rel in ('app.py', 'templates/home.html', 'templates/game.html'):
        contents[rel] = (root / rel).read_text(encoding='utf-8-sig')
    contents['app.py'] = patch_app(contents['app.py'])
    contents['templates/home.html'] = replace_marked_css(contents['templates/home.html'],
        'bounty-history-layout-v2', HISTORY_CSS)
    contents['templates/game.html'] = patch_game(contents['templates/game.html'])
    # Validate all in memory first: no partial modification on known structure failures.
    compile(contents['app.py'], 'app.py', 'exec')
    for rel, txt in contents.items():
        if rel.endswith('.html') and ('</head>' not in txt or '</html>' not in txt):
            raise ValueError('Unexpected template structure: ' + rel)
    modules = {}
    for name, value in EMBEDDED_FILES.items():
        decoded = zlib.decompress(base64.b64decode(value)).decode('utf-8')
        compile(decoded, name, 'exec')
        modules[name] = decoded

    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_base = root / '_bounty_upgrade_backups'
    backup = backup_base / stamp
    counter = 1
    while backup.exists():
        backup = backup_base / f'{stamp}_{counter:02d}'
        counter += 1
    backup.mkdir(parents=True, exist_ok=False)
    for rel in list(contents) + list(modules):
        target = root / rel
        if target.exists():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dst)
    database = root / 'bountycoders.db'
    if database.is_file():
        # Online SQLite backup is consistent even if a Flask process has DB open.
        try:
            src = sqlite3.connect(str(database), timeout=5)
            dst = sqlite3.connect(str(backup / 'bountycoders.db'))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        except sqlite3.Error as exc:
            raise RuntimeError('Database backup failed; no project files were changed: '+str(exc))

    for rel, txt in {**modules, **contents}.items():
        target = root / rel
        temp = target.with_name(target.name + '.bc_new')
        try:
            temp.write_text(txt, encoding='utf-8')
            os.replace(temp, target)
        finally:
            if temp.exists(): temp.unlink()
    print('\nSUCCESS! Updated:')
    for rel in (*contents, *modules):
        print(' - ' + rel)
    print('\nBackup location: ' + str(backup))
    print('\nDocker runner is the default (safe for other students\' code).')
    print('Install and start Docker Desktop, then pull the images:')
    print('  docker pull python:3.12-alpine')
    print('  docker pull eclipse-temurin:21-jdk')
    print('  docker pull gcc:14')
    print('\nFor a TRUSTED local demo only, you may use:')
    print('  $env:BC_RUNNER_MODE="host"; py app.py')
    print('\nRestart Flask and press Ctrl+F5 in the browser.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('\nERROR:', exc)
        sys.exit(1)
