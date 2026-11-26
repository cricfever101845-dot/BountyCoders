from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

import code_execution
import conftest


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self.body


@pytest.mark.parametrize(
    ("language", "compiler"),
    [("Python Basics", "python-3.14"), ("Java", "openjdk-25"), ("C language", "gcc-15")],
)
def test_compiler_ids_match_provider(language, compiler):
    assert code_execution.compiler_for_language(language) == compiler


def test_provider_request_keeps_key_server_side_and_normalizes_result(monkeypatch):
    monkeypatch.setenv("ONLINECOMPILER_API_KEY", "private-test-key")
    monkeypatch.setenv("CODE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("CODE_EXECUTION_PROVIDER", "onlinecompiler")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"output": "Hello\n", "error": "", "status": "success", "exit_code": 0, "time": "0.02"}).encode())

    monkeypatch.setattr(code_execution, "urlopen", fake_urlopen)
    result = conftest._real_execute_code("print('Hello')", "Python")
    assert result.output == "Hello\n"
    assert result.error is None
    assert result.ran is True
    assert captured["url"] == "https://api.onlinecompiler.io/api/run-code-sync/"
    assert captured["headers"]["Authorization"] == "private-test-key"
    assert captured["body"]["compiler"] == "python-3.14"
    assert captured["body"]["time_limit"] <= 30
    assert captured["timeout"] <= 45


def test_missing_key_is_provider_failure_and_does_not_call_network(monkeypatch):
    monkeypatch.delenv("ONLINECOMPILER_API_KEY", raising=False)
    monkeypatch.setattr(code_execution, "urlopen", lambda *_args, **_kwargs: pytest.fail("must not call provider"))
    with pytest.raises(code_execution.ProviderFailure) as error:
        conftest._real_execute_code("print('ok')", "Python")
    assert error.value.status == 503


def test_provider_rate_limit_is_infrastructure_failure(monkeypatch):
    monkeypatch.setenv("ONLINECOMPILER_API_KEY", "private-test-key")
    headers = Message()
    headers["Retry-After"] = "17"

    def rate_limited(*_args, **_kwargs):
        raise HTTPError(code_execution.API_URL, 429, "busy", headers, io.BytesIO(b""))

    monkeypatch.setattr(code_execution, "urlopen", rate_limited)
    with pytest.raises(code_execution.ProviderFailure) as error:
        conftest._real_execute_code("print('ok')", "Java")
    assert error.value.status == 429
    assert error.value.retry_after == "17"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"status": "compile_error", "exit_code": 1, "output": "", "error": "SyntaxError"}, "compilation_error"),
        ({"status": "error", "exit_code": 124, "output": "", "error": "time limit"}, "timeout"),
        ({"status": "error", "exit_code": 1, "output": "partial", "error": "crashed"}, "runtime_error"),
    ],
)
def test_real_program_failures_are_classified_as_user_execution_errors(monkeypatch, body, expected):
    monkeypatch.setenv("ONLINECOMPILER_API_KEY", "private-test-key")
    monkeypatch.setattr(code_execution, "urlopen", lambda *_args, **_kwargs: FakeResponse(json.dumps(body).encode()))
    result = conftest._real_execute_code("source", "C")
    assert result.ran is True
    assert result.error_type == expected


def test_code_and_input_bounds_are_checked_before_provider_call(monkeypatch):
    monkeypatch.setenv("ONLINECOMPILER_API_KEY", "private-test-key")
    monkeypatch.setattr(code_execution, "urlopen", lambda *_args, **_kwargs: pytest.fail("must not call provider"))
    with pytest.raises(ValueError, match="20 KB"):
        conftest._real_execute_code("x" * (20_001), "Python")
    with pytest.raises(ValueError, match="16 KB"):
        conftest._real_execute_code("print(1)", "Python", "x" * (16_001))
