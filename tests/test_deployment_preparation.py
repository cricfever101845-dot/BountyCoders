"""Targeted local checks for deployment-safe storage and request behavior."""
import importlib
import sys

import pytest


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "bounty-test.sqlite"))
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SERVICE_ROLE", "frontend")
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.app.config.update(TESTING=True)
    yield module
    sys.modules.pop("app", None)


def test_database_bootstrap_is_repeatable_and_preserves_users(app_module):
    conn = app_module.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, email, password, total_bounty) VALUES (?, ?, ?, ?)",
        ("test-cadet", "cadet@example.test", "test-hash", 123),
    )
    conn.commit()
    conn.close()

    app_module.init_db()

    conn = app_module.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, total_bounty FROM users WHERE email = ?", ("cadet@example.test",))
    user = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS count FROM questions")
    question_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM courses")
    course_count = cursor.fetchone()["count"]
    conn.close()

    assert user["username"] == "test-cadet"
    assert user["total_bounty"] == 123
    assert course_count == 4
    assert question_count == 60


def test_signup_progress_session_and_logout(app_module):
    client = app_module.app.test_client()
    response = client.post(
        "/signup",
        data={
            "username": "learning-cadet",
            "email": "Cadet@Example.test",
            "password": "long-test-password",
            "confirm_password": "long-test-password",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"learning-cadet" in response.data

    rejected_avatar = client.post(
        "/api/update_profile",
        json={"display_name": "Learning Cadet", "pirate_group": "Straw Hats", "avatar": "../../app.py"},
    )
    assert rejected_avatar.status_code == 400
    accepted_profile = client.post(
        "/api/update_profile",
        json={"display_name": "Learning Cadet", "pirate_group": "Straw Hats", "avatar": "sanji"},
    )
    assert accepted_profile.status_code == 200

    started = client.post("/api/start_session", json={"course_id": "101"})
    assert started.status_code == 200
    questions = started.json["session_questions"]
    assert {level: len(items) for level, items in questions.items()} == {
        "easy": 5, "medium": 5, "hard": 5
    }
    assert all("expected_output" not in item for items in questions.values() for item in items)

    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/home").status_code == 302


def test_health_readiness_and_authentication(app_module):
    client = app_module.app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/ready").json == {"status": "ready", "database": "connected"}
    assert client.get("/course_select").status_code == 302


def test_production_runner_does_not_execute_submitted_code(monkeypatch):
    from bounty_runner import run_student_code

    monkeypatch.setenv("ENVIRONMENT", "production")
    result = run_student_code("print('should not run')", "Python", None)
    assert result["error_type"] == "configuration_error"
    assert "isolated code runner" in result["error"]
