"""Portable Windows execution runner for BountyCoders.

Works only with developer-approved code on a private localhost college demo.
This IS NOT a sandbox. Student programs execute as the logged-in Windows user.
"""
from __future__ import annotations
import os
import re
import subprocess
import tempfile
from pathlib import Path

MAX_OUTPUT = 4000
MAX_INPUT = 20_000
PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_ROOT = Path(os.environ.get('BC_PORTABLE_ROOT') or (PROJECT_ROOT.parent if (PROJECT_ROOT.parent / 'runtime/python/python.exe').is_file() else PROJECT_ROOT / 'dist/BountyCoders_Submission_Windows_x64'))
PYTHON = DEMO_ROOT / 'runtime' / 'python' / 'python.exe'
JAVAC = DEMO_ROOT / 'tools' / 'jdk' / 'bin' / 'javac.exe'
JAVA = DEMO_ROOT / 'tools' / 'jdk' / 'bin' / 'java.exe'
TCC = DEMO_ROOT / 'tools' / 'tcc' / 'tcc.exe'


def _result(output='', error=None, error_type=None):
    return {'output': str(output or '')[:MAX_OUTPUT],
            'error': (str(error or '')[:MAX_OUTPUT] or None), 'error_type': error_type}


def _run(cmd, cwd, timeout, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    # Files avoid pipe handles held by compiler descendants and unbounded RAM use.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            p = subprocess.Popen([str(x) for x in cmd], cwd=str(cwd), env=env,
                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=5)
                return None, '', '', 'Time limit exceeded. Check for an infinite loop.'
            stdout.seek(0); stderr.seek(0)
            return (p.returncode, stdout.read(MAX_OUTPUT).decode('utf-8', 'replace'),
                    stderr.read(MAX_OUTPUT).decode('utf-8', 'replace'), None)
        except OSError as e:
            return None, '', '', 'Could not start compiler or program: ' + str(e)


def _checked(cmd, cwd, timeout, error_type, extra_env=None):
    status, output, error, problem = _run(cmd, cwd, timeout, extra_env)
    if problem:
        return _result(error=problem, error_type='timeout' if 'Time limit' in problem else 'configuration_error')
    if status != 0:
        return _result(output=output, error=error or output or f'Program exited with code {status}', error_type=error_type)
    return _result(output=output)


def run_student_code(code, language, legacy_host_runner):
    """Compile/run in a temporary directory, returning the legacy API response."""
    if not isinstance(code, str) or len(code.encode('utf-8')) > MAX_INPUT:
        return _result(error='Code must be text under 20 KB.', error_type='configuration_error')
    lang = (language or '').strip().lower()
    if lang in ('html and css', 'html/css'):
        return _result(output=code)
    mode = os.environ.get('BC_RUNNER_MODE', 'portable').strip().lower()
    if mode != 'portable':
        return _result(error='This submission build requires BC_RUNNER_MODE=portable.', error_type='configuration_error')

    with tempfile.TemporaryDirectory(prefix='bounty_code_') as tmp:
        folder = Path(tmp)
        if lang in ('python', 'python basics'):
            if not PYTHON.is_file():
                return _result(error='Portable Python runtime missing.', error_type='configuration_error')
            src = folder / 'main.py'
            src.write_text(code, encoding='utf-8')
            result = _checked([PYTHON, '-I', '-B', src], folder, 8, 'runtime_error')
            err = result.get('error') or ''
            if any(s in err for s in ('SyntaxError:', 'IndentationError:', 'TabError:')):
                result['error_type'] = 'compilation_error'
            return result

        if lang in ('java', 'java basics'):
            if not JAVAC.is_file() or not JAVA.is_file():
                return _result(error='Portable Java JDK missing.', error_type='configuration_error')
            package = re.search(r'^\s*package\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*;', code, re.M)
            public = re.search(r'\bpublic\s+class\s+([a-zA-Z_]\w*)', code)
            cls = public or re.search(r'\bclass\s+([a-zA-Z_]\w*)', code)
            classname = cls.group(1) if cls else 'Main'
            path = folder / f'{classname}.java'
            path.write_text(code, encoding='utf-8')
            compilation = _checked([JAVAC, '-encoding', 'UTF-8', '-d', folder, path],
                                   folder, 20, 'compilation_error')
            if compilation['error']:
                return compilation
            qualified = (package.group(1) + '.' if package else '') + classname
            return _checked([JAVA, '-Xmx128m', '-cp', folder, qualified], folder, 10, 'runtime_error')

        if lang in ('c', 'c language'):
            if not TCC.is_file():
                return _result(error='Portable C compiler missing.', error_type='configuration_error')
            src, dest = folder / 'main.c', folder / 'main.exe'
            src.write_text(code, encoding='utf-8')
            compilation = _checked([TCC, '-B' + str(TCC.parent), src, '-o', dest],
                                   folder, 15, 'compilation_error')
            if compilation['error']:
                return compilation
            if not dest.is_file():
                return _result(error='C compiler did not produce an executable.', error_type='compilation_error')
            return _checked([dest], folder, 10, 'runtime_error')

    return _result(error=f'Unsupported language: {language}', error_type='unsupported_language')
