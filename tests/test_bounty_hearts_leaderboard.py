from __future__ import annotations

import uuid

import pytest

import code_execution
from code_execution import ExecutionResult, ProviderFailure
from app import app, get_db


@pytest.fixture
def player():
    uid = 10_000 + uuid.uuid4().int % 1_000_000
    username = "pirate_" + uuid.uuid4().hex[:12]
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users(id,username,email,password,total_bounty) VALUES(?,?,?,?,0)",
            (uid, username, username + "@example.test", "test-only"),
        )
        cursor.execute(
            "INSERT INTO user_profiles(user_id,display_name,pirate_group,avatar) VALUES(?,?,?,?)",
            (uid, username, "Test crew", "luffy"),
        )
        conn.commit()
    finally:
        conn.close()
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = uid
        browser_session["username"] = username
    start = client.post("/api/start_session", json={"course_id": "101", "force_new": True})
    assert start.status_code == 200
    assert start.get_json()["hearts_remaining"] == 3
    result = {"uid": uid, "username": username, "client": client, "start": start.get_json()}
    yield result
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bounty_records WHERE user_id=?", (uid,))
        cursor.execute("DELETE FROM progress WHERE user_id=?", (uid,))
        cursor.execute("DELETE FROM question_rotation WHERE user_id=?", (uid,))
        cursor.execute("DELETE FROM user_profiles WHERE user_id=?", (uid,))
        cursor.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()


def set_run(monkeypatch, output="OK", error=None, error_type=None, ran=True):
    monkeypatch.setattr(
        code_execution,
        "TEST_EXECUTION_OVERRIDE",
        lambda code, language, stdin: ExecutionResult(output, error, error_type, ran, "0.001"),
        raising=False,
    )


def answer(client, level, number, code="pass", request_id=None, course_id="101"):
    return client.post(
        "/api/submit_answer",
        json={
            "request_id": request_id or uuid.uuid4().hex,
            "course_id": course_id,
            "level": level,
            "question_number": number,
            "code": code,
        },
    )


def test_run_code_is_separate_and_does_not_change_hearts_or_bounty(player, monkeypatch):
    set_run(monkeypatch, output="practice output")
    response = player["client"].post(
        "/api/run_code",
        json={"request_id": "run-practice", "course_id": "101", "level": "easy", "question_number": 1, "code": "print('hello')"},
    )
    assert response.status_code == 200
    assert response.get_json()["output"] == "practice output"
    state = player["client"].get("/api/game_state?course_id=101").get_json()
    assert state["hearts_remaining"] == 3
    assert state["difficulty_bounty"] == 0
    assert state["total_bounty"] == 0


def test_provider_failure_does_not_cost_a_heart_or_bounty(player, monkeypatch):
    def unavailable(code, language, stdin):
        raise ProviderFailure("Provider offline", status=503)

    monkeypatch.setattr(code_execution, "TEST_EXECUTION_OVERRIDE", unavailable, raising=False)
    response = answer(player["client"], "easy", 1, request_id="provider-failure")
    assert response.status_code == 503
    assert response.get_json()["provider_error"] is True
    state = player["client"].get("/api/game_state?course_id=101").get_json()
    assert state["hearts_remaining"] == 3
    assert state["difficulty_bounty"] == 0
    assert state["total_bounty"] == 0


def test_compile_error_is_an_incorrect_final_submission(player, monkeypatch):
    set_run(monkeypatch, output="", error="SyntaxError: invalid syntax", error_type="compilation_error")
    response = answer(player["client"], "easy", 1)
    assert response.status_code == 200
    data = response.get_json()
    assert data["correct"] is False
    assert data["error_type"] == "compilation_error"
    assert data["hearts_remaining"] == 2
    assert data["bounty_lost"] == 1_000_000
    assert player["client"].get("/api/game_state?course_id=101").get_json()["total_bounty"] == 0


def test_refresh_restores_server_saved_hearts_and_current_difficulty_bounty(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    assert answer(player["client"], "easy", 1).get_json()["correct"] is True
    set_run(monkeypatch, output="wrong")
    wrong = answer(player["client"], "easy", 2).get_json()
    assert wrong["hearts_remaining"] == 2
    resumed = player["client"].post("/api/start_session", json={"course_id": "101"}).get_json()
    assert resumed["resumed"] is True
    assert resumed["hearts_remaining"] == 2
    assert resumed["difficulty_bounty"] == 4_000_000
    assert resumed["current_question_number"] == 2


def test_three_incorrect_submissions_end_attempt_and_retry_is_persistent(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    first = answer(player["client"], "easy", 1)
    assert first.status_code == 200 and first.get_json()["correct"] is True
    assert first.get_json()["bounty_gained"] == 5_000_000
    assert first.get_json()["difficulty_bounty"] == 5_000_000

    set_run(monkeypatch, output="not the answer")
    one = answer(player["client"], "easy", 2)
    two = answer(player["client"], "easy", 2)
    three = answer(player["client"], "easy", 2)
    assert [one.get_json()["hearts_remaining"], two.get_json()["hearts_remaining"], three.get_json()["hearts_remaining"]] == [2, 1, 0]
    assert one.get_json()["bounty_lost"] == 1_000_000
    assert three.get_json()["attempt_failed"] is True
    assert three.get_json()["difficulty_bounty"] == 0
    state = player["client"].get("/api/game_state?course_id=101").get_json()
    assert state["attempt_status"] == "failed"
    assert state["current_question_number"] == 1
    assert state["hearts_remaining"] == 0
    assert state["difficulty_bounty"] == 0
    assert state["total_bounty"] == 0  # wrong-answer deductions and the failed attempt reset

    retry = player["client"].post("/api/retry_difficulty", json={"course_id": "101"})
    assert retry.status_code == 200
    assert retry.get_json()["hearts_remaining"] == 3
    assert retry.get_json()["attempt_number"] == 2
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status,hearts_remaining,bounty_earned FROM difficulty_attempts WHERE user_id=? ORDER BY id", (player["uid"],))
        attempts = cursor.fetchall()
        assert len(attempts) == 2
        assert (attempts[0]["status"], attempts[0]["hearts_remaining"], attempts[0]["bounty_earned"]) == ("failed", 0, 0)
        assert attempts[1]["status"] == "active"
    finally:
        conn.close()


def test_completed_difficulty_best_survives_a_later_difficulty_failure(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    for question in range(1, 6):
        response = answer(player["client"], "easy", question)
        assert response.status_code == 200 and response.get_json()["correct"] is True
    assert response.get_json()["difficulty_completed"] is True
    assert response.get_json()["difficulty_bounty"] == 25_000_000

    set_run(monkeypatch, output="wrong")
    for _ in range(3):
        failed = answer(player["client"], "medium", 1)
    assert failed.get_json()["attempt_failed"] is True
    easy = player["client"].get("/api/leaderboard?difficulty=easy").get_json()
    overall = player["client"].get("/api/leaderboard?difficulty=overall").get_json()
    assert next(row for row in easy["entries"] if row["user"])["bounty"] == 25_000_000
    assert next(row for row in overall["entries"] if row["user"])["bounty"] == 25_000_000


def test_full_course_earns_exact_difficulty_and_overall_scores(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    last = None
    for level in ("easy", "medium", "hard"):
        for question in range(1, 6):
            last = answer(player["client"], level, question)
            assert last.status_code == 200
            assert last.get_json()["correct"] is True
            assert last.get_json()["bounty_gained"] == {"easy": 5_000_000, "medium": 10_000_000, "hard": 15_000_000}[level]
            if question == 1:
                assert last.get_json()["hearts_remaining"] == 3
    assert last.get_json()["completed"] is True
    board = player["client"].get("/api/leaderboard?difficulty=overall").get_json()
    row = next(item for item in board["entries"] if item["user"])
    assert row["bounty"] == 150_000_000
    for level, expected in (("easy", 25_000_000), ("medium", 50_000_000), ("hard", 75_000_000)):
        result = player["client"].get(f"/api/leaderboard?difficulty={level}").get_json()
        assert next(item for item in result["entries"] if item["user"])["bounty"] == expected


def test_request_replay_cannot_award_twice(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    first = answer(player["client"], "easy", 1, request_id="same-submit")
    replay = answer(player["client"], "easy", 1, request_id="same-submit")
    assert first.status_code == replay.status_code == 200
    assert replay.get_json() == first.get_json()
    state = player["client"].get("/api/game_state?course_id=101").get_json()
    assert state["total_bounty"] == 5_000_000
    assert state["current_question_number"] == 2


@pytest.mark.parametrize("limit_key", ["CODE_EXECUTION_PER_HOUR", "CODE_EXECUTION_PER_DAY", "CODE_EXECUTION_PER_MONTH"])
def test_execution_rate_limits_return_without_penalty(player, monkeypatch, limit_key):
    monkeypatch.setenv(limit_key, "1")
    if limit_key == "CODE_EXECUTION_PER_MONTH":
        # This quota is global, so clear earlier test runs in the isolated test DB.
        conn = get_db()
        try:
            conn.execute("DELETE FROM execution_requests")
            conn.commit()
        finally:
            conn.close()
    set_run(monkeypatch, output="practice")
    payload = {"course_id": "101", "level": "easy", "question_number": 1, "code": "print(1)"}
    first = player["client"].post("/api/run_code", json={**payload, "request_id": "quota-one"})
    second = player["client"].post("/api/run_code", json={**payload, "request_id": "quota-two"})
    assert first.status_code == 200
    assert second.status_code == 429
    state = player["client"].get("/api/game_state?course_id=101").get_json()
    assert state["hearts_remaining"] == 3
    assert state["total_bounty"] == 0


def test_personal_best_keeps_the_higher_completed_attempt(player, monkeypatch):
    set_run(monkeypatch, output="OK")
    for question in range(1, 6):
        answer(player["client"], "easy", question)
    # The next completed Easy attempt has one penalty, so it is 1M lower.
    start = player["client"].post("/api/start_session", json={"course_id": "102", "force_new": True})
    assert start.status_code == 200
    set_run(monkeypatch, output="OK")
    assert answer(player["client"], "easy", 1, course_id="102").get_json()["correct"] is True
    set_run(monkeypatch, output="wrong")
    assert answer(player["client"], "easy", 2, course_id="102").get_json()["hearts_remaining"] == 2
    set_run(monkeypatch, output="OK")
    for question in range(2, 6):
        result = answer(player["client"], "easy", question, course_id="102")
    assert result.get_json()["difficulty_bounty"] == 24_000_000
    board = player["client"].get("/api/leaderboard?difficulty=easy").get_json()
    assert next(row for row in board["entries"] if row["user"])["bounty"] == 25_000_000


def test_leaderboard_and_game_controls_render_for_mobile(player):
    board = player["client"].get("/leaderboard")
    game = player["client"].get("/game/101")
    assert board.status_code == 200
    assert game.status_code == 200
    page = game.get_data(as_text=True)
    assert "Run Code" in page
    assert "Submit Answer" in page
    assert "orientation-hint" in page
    assert "orientation: portrait" in page
    assert "bc-code-draft-" in page


def test_random_question_pool_and_resume(player):
    client = player["client"]
    original = player["start"]["session_questions"]
    for level, questions in original.items():
        assert len(questions) == 5
        assert len({(q["id"], q["alt"]) for q in questions}) == 5
        assert len({" ".join(q["question_text"].split()).casefold() for q in questions}) == 5
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE course_id=? AND level=? ORDER BY question_number", ("101", level))
            rows = cursor.fetchall()
            source = {row["id"]: row for row in rows}
            for i, q in enumerate(questions):
                assert q["question_text"] == source[q["id"]][f'question_text_{q["alt"]}']
                assert q["opponent_name"] == rows[i]["opponent_name"]
                assert "expected_output" not in q
        finally:
            conn.close()
    resumed = client.post("/api/start_session", json={"course_id": "101"}).get_json()
    assert resumed["session_questions"] == original
    fresh = client.post("/api/start_session", json={"course_id": "101", "force_new": True}).get_json()
    for level in original:
        assert not ({(q["id"], q["alt"]) for q in original[level]} &
                    {(q["id"], q["alt"]) for q in fresh["session_questions"][level]})


def test_retry_randomizes_only_failed_difficulty(player, monkeypatch):
    client = player["client"]
    original = player["start"]["session_questions"]
    set_run(monkeypatch, output="wrong")
    for _ in range(3):
        response = answer(client, "easy", 1)
        assert response.status_code == 200
        assert not response.get_json()["correct"]
    retry = client.post("/api/retry_difficulty", json={"course_id": "101"})
    assert retry.status_code == 200
    data = retry.get_json()
    assert data["hearts_remaining"] == 3
    assert data["difficulty_bounty"] == 0
    fresh = data["session_questions"]
    assert fresh["medium"] == original["medium"]
    assert fresh["hard"] == original["hard"]
    assert not ({(q["id"], q["alt"]) for q in original["easy"]} &
                {(q["id"], q["alt"]) for q in fresh["easy"]})
    resumed = client.post("/api/start_session", json={"course_id": "101"}).get_json()
    assert resumed["session_questions"] == fresh


def test_rotate_uses_unused_pool_variant_and_rejects_stale_question(player, monkeypatch):
    client = player["client"]
    original = player["start"]["session_questions"]["easy"]
    result = client.post("/api/get_questions", json={"course_id": "101", "level": "easy", "question_number": 1})
    assert result.status_code == 200
    replacement = result.get_json()["question"]
    assert (replacement["id"], replacement["alt"]) not in {(q["id"], q["alt"]) for q in original}
    assert replacement["opponent_name"] == original[0]["opponent_name"]
    stale = client.post("/api/submit_answer", json={"course_id": "101", "level": "easy", "question_number": 1,
                         "question_id": original[0]["id"], "question_alt": original[0]["alt"], "code": "pass"})
    assert stale.status_code == 409
    set_run(monkeypatch, output="OK")
    accepted = client.post("/api/submit_answer", json={"course_id": "101", "level": "easy", "question_number": 1,
                            "question_id": replacement["id"], "question_alt": replacement["alt"], "code": "pass"})
    assert accepted.status_code == 200
    assert accepted.get_json()["correct"]
    assert accepted.get_json()["bounty_gained"] == 5_000_000
