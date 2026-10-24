"""Launch the bundled, local-only BountyCoders web app in a browser."""
from __future__ import annotations
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app'
RUNTIME = ROOT / 'runtime' / 'python' / 'python.exe'


def port_available():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    print('=== BountyCoders | Portable College Submission ===', flush=True)
    for file in (APP / 'app.py', APP / 'bountycoders.db', RUNTIME):
        if not file.is_file():
            raise FileNotFoundError(f'Submission package is missing: {file}')
    state = Path(os.environ.get('BOUNTY_STATE_DIR') or APP / 'demo_data')
    state.mkdir(parents=True, exist_ok=True)
    keyfile = state / 'session_secret.txt'
    if not keyfile.exists():
        keyfile.write_text(secrets.token_hex(32), encoding='ascii')
    port = port_available()
    env = os.environ.copy()
    env.update({
        'BC_RUNNER_MODE': 'portable',
        'BOUNTY_SECRET_KEY': keyfile.read_text(encoding='ascii').strip(),
        'BOUNTY_PORT': str(port),
        'PYTHONUTF8': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
    })
    url = f'http://127.0.0.1:{port}/'
    print('Starting private local server ...', flush=True)
    proc = subprocess.Popen([str(RUNTIME), '-B', 'app.py'], cwd=str(APP), env=env)
    try:
        for _ in range(120):
            if proc.poll() is not None:
                raise RuntimeError(f'Server stopped unexpectedly (exit {proc.returncode})')
            try:
                with urlopen(url, timeout=0.6) as response:
                    if response.status < 500:
                        print('\nBountyCoders is ready: ' + url, flush=True)
                        webbrowser.open(url)
                        print('Keep this window open. Press Ctrl+C to stop.', flush=True)
                        break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError('Server was not ready. Check the console errors above.')
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print('\nBountyCoders stopped.')
    except Exception as e:
        print('ERROR:', e)
        input('Press Enter to close...')
        sys.exit(1)
