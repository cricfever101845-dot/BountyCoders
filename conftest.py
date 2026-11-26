"""Keep integration tests isolated from local user data and host compilers."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="bounty-coders-tests-"))
os.environ["BCTEST_DISABLE_DOTENV"] = "1"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ONLINECOMPILER_API_KEY", None)
os.environ["SQLITE_PATH"] = str(_TEST_DATA_DIR / "test.sqlite3")
os.environ["ENVIRONMENT"] = "development"
os.environ["SERVICE_ROLE"] = "frontend"


# Progression tests exercise grading state transitions with known "OK" output.
# Keep arbitrary code execution out of those tests; the runner has its own
# production-disabled check and must never depend on a host compiler being set up.
import bounty_runner
import code_execution
from code_execution import ExecutionResult

_real_runner = bounty_runner.run_student_code


def _test_runner(code, language, legacy_host_runner):
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
        return _real_runner(code, language, legacy_host_runner)
    if isinstance(code, str) and len(code.encode("utf-8")) <= bounty_runner.MAX_INPUT:
        return {"output": "OK", "error": None, "error_type": None}
    return _real_runner(code, language, legacy_host_runner)


bounty_runner.run_student_code = _test_runner

_real_execute_code = code_execution.execute_code


def _test_execute_code(code, language, stdin=""):
    override = getattr(code_execution, "TEST_EXECUTION_OVERRIDE", None)
    if override is not None:
        return override(code, language, stdin) if callable(override) else override
    if isinstance(code, str) and len(code.encode("utf-8")) <= code_execution.MAX_CODE_BYTES:
        return ExecutionResult(output="OK", error=None, error_type=None, ran=True, execution_time="0.001")
    raise ValueError("Invalid test code")


code_execution.execute_code = _test_execute_code


def pytest_sessionstart(session):
    """Seed the legacy UI tests' expected sample account in this temporary DB."""
    import app

    conn = app.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (id, username, email, password, total_bounty) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, "testpirate", "testpirate@example.test", "test-only", 75_000_000),
        )
        cursor.execute(
            "INSERT INTO user_profiles (user_id, display_name, pirate_group, avatar) "
            "VALUES (?, ?, ?, ?)",
            (1, "Test Pirate", "Straw Hat Pirates", "luffy"),
        )
        cursor.execute(
            "INSERT INTO progress (user_id, course_id, current_level, current_question_number, "
            "completed, session_questions, bounty_earned) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "101", "hard", 5, 1, "{}", 75_000_000),
        )
        cursor.execute(
            "INSERT INTO bounty_records (user_id, course_id, course_name, bounty) "
            "VALUES (?, ?, ?, ?)",
            (1, "101", "Python Basics", 75_000_000),
        )
        cursor.execute(
            "UPDATE questions SET expected_output_1 = 'OK', expected_output_2 = 'OK', "
            "expected_output_3 = 'OK'"
        )
        conn.commit()
    finally:
        conn.close()
