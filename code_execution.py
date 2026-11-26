"""Server-side OnlineCompiler.io adapter; submitted code is never run in this app."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.onlinecompiler.io/api/run-code-sync/"
MAX_CODE_BYTES = 20_000
MAX_INPUT_BYTES = 16_000
MAX_OUTPUT_CHARS = 8_000
COMPILERS = {
    "python": "python-3.14",
    "python basics": "python-3.14",
    "java": "openjdk-25",
    "java basics": "openjdk-25",
    "c": "gcc-15",
    "c language": "gcc-15",
}


class ProviderFailure(Exception):
    """An infrastructure/configuration failure that must not cost a heart."""

    def __init__(self, message: str, *, status: int = 503, retry_after: str | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class ExecutionResult:
    output: str
    error: str | None
    error_type: str | None
    ran: bool
    execution_time: str | None = None


def compiler_for_language(language: str) -> str:
    compiler = COMPILERS.get((language or "").strip().casefold())
    if not compiler:
        raise ValueError("Code execution is available for Python, Java, and C questions.")
    return compiler


def _classify_program_error(body: dict, exit_code: int | None) -> str | None:
    status = str(body.get("status") or "").casefold()
    error = str(body.get("error") or "")
    if exit_code == 0 and status in ("success", "completed", "ok", ""):
        return None
    if exit_code == 124 or "time limit" in error.casefold() or "timed out" in error.casefold():
        return "timeout"
    if status in ("compile_error", "compilation_error") or re.search(
        r"syntaxerror|indentationerror|compilation failed|error:|cannot find symbol|expected ';'",
        error,
        flags=re.IGNORECASE,
    ):
        return "compilation_error"
    return "runtime_error"


def execute_code(code: str, language: str, stdin: str = "") -> ExecutionResult:
    """Execute a single snippet in the provider's isolated sandbox."""
    key = os.environ.get("ONLINECOMPILER_API_KEY", "").strip()
    provider = os.environ.get("CODE_EXECUTION_PROVIDER", "onlinecompiler").strip().casefold()
    if provider != "onlinecompiler":
        raise ProviderFailure("The configured code execution provider is unsupported.", status=503)
    if not key:
        raise ProviderFailure("Code execution is not configured yet.", status=503)
    if os.environ.get("CODE_EXECUTION_ENABLED", "true").strip().casefold() not in ("1", "true", "yes", "on"):
        raise ProviderFailure("Code execution is temporarily disabled.", status=503)
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Write some code before running it.")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Code is too long (20 KB maximum).")
    if not isinstance(stdin, str) or len(stdin.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Input is too long (16 KB maximum).")
    if "\x00" in code or "\x00" in stdin:
        raise ValueError("Code and input must not contain NUL characters.")

    compiler = compiler_for_language(language)
    time_limit = max(1, min(int(os.environ.get("CODE_EXECUTION_TIME_LIMIT", "8")), 30))
    payload = json.dumps({
        "compiler": compiler,
        "code": code,
        "input": stdin,
        "time_limit": time_limit,
    }).encode("utf-8")
    request = Request(
        API_URL,
        data=payload,
        headers={"Authorization": key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    request_timeout = max(10, min(int(os.environ.get("CODE_EXECUTION_REQUEST_TIMEOUT", "40")), 45))
    try:
        with urlopen(request, timeout=request_timeout) as response:
            raw = response.read(96_000)
            if len(raw) >= 96_000:
                raise ProviderFailure("The code service returned an oversized response.")
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        # Provider rejections are service-side failures unless the HTTP response
        # explicitly represents an executed program result (normally HTTP 200).
        if exc.code == 429:
            raise ProviderFailure("The code service is busy or its account limit was reached. Please retry shortly.", status=429, retry_after=retry_after) from exc
        if exc.code in (401, 403):
            raise ProviderFailure("The code execution API key is missing or invalid.", status=503) from exc
        raise ProviderFailure("The code service could not accept this run. Please retry.", status=503) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderFailure("The code service is temporarily unavailable. Please retry.", status=503) from exc

    try:
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("Response is not a JSON object")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProviderFailure("The code service returned an invalid response. Please retry.", status=503) from exc

    provider_error = str(result.get("error") or "").casefold()
    if "internal error: code execution failed" in provider_error or str(result.get("status") or "").casefold() in ("internal_error", "service_error", "failed_to_run"):
        raise ProviderFailure("The code service failed while starting this run. No answer was scored; please retry.", status=503)

    output = str(result.get("output") or "")[:MAX_OUTPUT_CHARS]
    error = str(result.get("error") or "")[:MAX_OUTPUT_CHARS] or None
    try:
        exit_code = int(result["exit_code"]) if result.get("exit_code") is not None else None
    except (ValueError, TypeError):
        exit_code = None
    error_type = _classify_program_error(result, exit_code)
    if exit_code is None and str(result.get("status") or "").casefold() not in (
        "success", "completed", "ok", "compile_error", "compilation_error", "runtime_error", "timeout"
    ):
        # Unknown provider statuses are infrastructure errors, not wrong answers.
        raise ProviderFailure("The code service returned an incomplete run status. Please retry.", status=503)
    return ExecutionResult(
        output=output,
        error=error if error_type else None,
        error_type=error_type,
        ran=True,
        execution_time=str(result.get("time") or "")[:32] or None,
    )
