"""Server-authoritative course attempts, hearts, bounty scoring and leaderboards."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from flask import jsonify, render_template, request, session

LEVELS = ("easy", "medium", "hard")
REWARDS = {"easy": 5_000_000, "medium": 10_000_000, "hard": 15_000_000}
WRONG_ANSWER_PENALTY = 1_000_000
STARTING_HEARTS = 3
REQUEST_LOCK_ID = 914_205_772


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _decode_json(value, default):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, (dict, list)) else default
    except (TypeError, ValueError):
        return default


def _fingerprint(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def install(app, get_db, run_code=None, compare_outputs=None, classify_error=None, evaluate_html=None):
    """Install server-owned game routes on the existing Flask application."""
    from database import is_postgres_enabled
    from code_execution import ProviderFailure, execute_code

    def get_json():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def user_id_or_response():
        value = session.get("user_id")
        if value is None:
            return None, (jsonify(error="Not logged in"), 401)
        try:
            return int(value), None
        except (TypeError, ValueError):
            session.clear()
            return None, (jsonify(error="Please sign in again."), 401)

    def public_session(questions):
        # Never serialize expected output, grading rules, or hidden input cases.
        return {
            level: [
                {key: q[key] for key in ("id", "question_text", "opponent_name", "language", "alt") if key in q}
                for q in questions.get(level, [])
            ]
            for level in LEVELS
        }

    def question_key(question):
        return (str(question["id"]), int(question["alt"]))

    def question_text_key(question):
        return " ".join(question["question_text"].split()).casefold()

    def difficulty_pool(cursor, course_id, level):
        cursor.execute(
            "SELECT * FROM questions WHERE course_id=? AND level=? ORDER BY question_number,id",
            (course_id, level),
        )
        rows = cursor.fetchall()
        # Original five map slots keep their own opponents even if questions
        # are sampled from a different source group in this difficulty.
        slot_rows = {int(row["question_number"]): row for row in rows}
        if not all(n in slot_rows for n in range(1, 6)):
            raise RuntimeError(f"Question bank for {level} is missing map slots.")
        pool = []
        seen_text = set()
        for row in rows:
            for alt in (1, 2, 3):
                text = row[f"question_text_{alt}"]
                expected = row[f"expected_output_{alt}"]
                if not text or not expected:
                    continue
                question = {
                    "id": row["id"], "question_text": text,
                    "opponent_name": row["opponent_name"],
                    "language": row["language"], "alt": alt,
                }
                key = question_text_key(question)
                if key not in seen_text:
                    pool.append(question)
                    seen_text.add(key)
        if len(pool) < 5:
            raise RuntimeError(f"Question bank for {level} must contain at least five distinct questions.")
        return pool, [slot_rows[n]["opponent_name"] for n in range(1, 6)]

    def sample_difficulty(cursor, course_id, level, previous=()):
        pool, opponents = difficulty_pool(cursor, course_id, level)
        old_keys = {question_key(q) for q in previous}
        old_texts = {question_text_key(q) for q in previous}
        fresh = [q for q in pool if question_key(q) not in old_keys and question_text_key(q) not in old_texts]
        rng = random.SystemRandom()
        # With the built-in 15-question bank, retries can avoid all five
        # immediately preceding questions. Smaller custom banks reuse only
        # the minimum required number.
        selected = rng.sample(fresh, min(5, len(fresh)))
        if len(selected) < 5:
            used = {question_key(q) for q in selected}
            selected += rng.sample([q for q in pool if question_key(q) not in used], 5 - len(selected))
        rng.shuffle(selected)
        return [dict(q, opponent_name=opponents[i]) for i, q in enumerate(selected)]

    def latest_progress(cursor, uid, course_id):
        cursor.execute(
            "SELECT * FROM progress WHERE user_id=? AND course_id=? AND completed=0 ORDER BY id DESC LIMIT 1",
            (uid, course_id),
        )
        return cursor.fetchone()

    def latest_attempt(cursor, progress_id, level):
        cursor.execute(
            """SELECT * FROM difficulty_attempts WHERE progress_id=? AND difficulty=?
               ORDER BY attempt_number DESC LIMIT 1""",
            (progress_id, level),
        )
        return cursor.fetchone()

    def ensure_active_attempt(cursor, progress, uid, course_id):
        level = progress["current_level"]
        attempt = latest_attempt(cursor, progress["id"], level)
        if attempt is None:
            cursor.execute(
                """INSERT INTO difficulty_attempts
                   (progress_id,user_id,course_id,difficulty,attempt_number,hearts_remaining,bounty_earned,status)
                   VALUES (?,?,?,?,?,?,0,'active')""",
                (progress["id"], uid, course_id, level, 1, STARTING_HEARTS),
            )
            attempt = latest_attempt(cursor, progress["id"], level)
        return attempt

    def game_state(cursor, progress, uid, course_id):
        attempt = ensure_active_attempt(cursor, progress, uid, course_id)
        cursor.execute("SELECT total_bounty FROM users WHERE id=?", (uid,))
        user = cursor.fetchone()
        return {
            "current_level": progress["current_level"],
            "current_question_number": int(progress["current_question_number"]),
            "bounty_earned": int(progress["bounty_earned"] or 0),
            "difficulty_bounty": int(attempt["bounty_earned"] or 0),
            "hearts_remaining": int(attempt["hearts_remaining"]),
            "attempt_number": int(attempt["attempt_number"]),
            "attempt_status": attempt["status"],
            "completed": bool(progress["completed"]),
            "total_bounty": int(user["total_bounty"] if user else 0),
        }

    def fetch_questions(cursor, uid, course_id, previous=None):
        previous = previous or {}
        return {level: sample_difficulty(cursor, course_id, level, previous.get(level, [])) for level in LEVELS}

    def start_session():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        data = get_json()
        course_id = str(data.get("course_id") or "").strip()
        force_new = data.get("force_new") is True
        if not course_id:
            return jsonify(error="Missing course ID"), 400
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT id FROM courses WHERE id=?", (course_id,))
            if not cursor.fetchone():
                conn.rollback()
                return jsonify(error="Course not found"), 404

            latest = latest_progress(cursor, uid, course_id)
            existing = None if force_new else latest
            if existing is not None:
                questions = _decode_json(existing["session_questions"], {})
                if any(len(questions.get(level, [])) != 5 for level in LEVELS):
                    conn.rollback()
                    return jsonify(error="Saved questions are damaged. Start a new journey."), 409
                state = game_state(cursor, existing, uid, course_id)
                conn.commit()
                return jsonify(resumed=True, session_questions=public_session(questions), **state)

            previous = _decode_json(latest["session_questions"], {}) if latest else {}
            questions = fetch_questions(cursor, uid, course_id, previous)
            cursor.execute(
                """INSERT INTO progress
                   (user_id,course_id,current_level,current_question_number,completed,session_questions,bounty_earned)
                   VALUES (?,?, 'easy',1,0,?,0) RETURNING id""",
                (uid, course_id, json.dumps(questions)),
            )
            progress_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO difficulty_attempts
                   (progress_id,user_id,course_id,difficulty,attempt_number,hearts_remaining,bounty_earned,status)
                   VALUES (?,?,?,'easy',1,?,0,'active')""",
                (progress_id, uid, course_id, STARTING_HEARTS),
            )
            cursor.execute("SELECT * FROM progress WHERE id=?", (progress_id,))
            progress = cursor.fetchone()
            state = game_state(cursor, progress, uid, course_id)
            conn.commit()
            return jsonify(resumed=False, session_questions=public_session(questions), **state)
        except RuntimeError as exc:
            conn.rollback()
            logging.getLogger(__name__).warning("Course question data unavailable: %s", exc)
            return jsonify(error="The question bank is not ready for this course."), 500
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not start course")
            return jsonify(error="Could not start the course right now. Please retry."), 500
        finally:
            conn.close()

    def rotate_question():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        data = get_json()
        course_id = str(data.get("course_id") or "").strip()
        level = str(data.get("level") or "").lower()
        try:
            number = int(data.get("question_number"))
        except (ValueError, TypeError):
            return jsonify(error="Invalid question number"), 400
        if level not in LEVELS or not 1 <= number <= 5:
            return jsonify(error="Invalid level or question number"), 400
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            lock_execution_counter(cursor)
            progress = latest_progress(cursor, uid, course_id)
            if not progress or progress["current_level"] != level or int(progress["current_question_number"]) != number:
                conn.rollback()
                return jsonify(error="You can only retry the active question."), 409
            attempt = ensure_active_attempt(cursor, progress, uid, course_id)
            if attempt["status"] != "active":
                conn.rollback()
                return jsonify(error="Retry the difficulty before changing this question."), 409
            saved = _decode_json(progress["session_questions"], {})
            selected = saved.get(level, [])
            if len(selected) != 5:
                conn.rollback()
                return jsonify(error="Saved questions are damaged. Reload the game."), 409
            pool, opponents = difficulty_pool(cursor, course_id, level)
            used_keys = {question_key(q) for q in selected}
            used_texts = {question_text_key(q) for q in selected}
            candidates = [q for q in pool if question_key(q) not in used_keys and question_text_key(q) not in used_texts]
            if not candidates:
                conn.rollback()
                return jsonify(error="No unused question is available in this difficulty."), 409
            question = dict(random.SystemRandom().choice(candidates), opponent_name=opponents[number - 1])
            saved[level][number - 1] = question
            cursor.execute(
                "UPDATE progress SET session_questions=?,last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(saved), progress["id"]),
            )
            conn.commit()
            return jsonify(question=question, success=True)
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not rotate the active question")
            return jsonify(error="Could not load another question right now. Please retry."), 500
        finally:
            conn.close()

    def lock_execution_counter(cursor):
        if is_postgres_enabled():
            cursor.execute("SELECT pg_advisory_xact_lock(?)", (REQUEST_LOCK_ID,))

    def quota_limits():
        return (
            max(1, int(os.environ.get("CODE_EXECUTION_PER_HOUR", "30"))),
            max(1, int(os.environ.get("CODE_EXECUTION_PER_DAY", "100"))),
            max(1, int(os.environ.get("CODE_EXECUTION_PER_MONTH", "80000"))),
        )

    def replay_request(uid, operation, payload):
        raw_id = str(get_json().get("request_id") or "").strip()[:100]
        if not raw_id:
            return None
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM execution_requests WHERE request_id=?", (raw_id,))
            row = cursor.fetchone()
            if not row:
                return None
            if int(row["user_id"]) != uid or row["operation"] != operation or row["payload_hash"] != _fingerprint(payload):
                return jsonify(error="This request ID was already used for a different action."), 409
            if not row["response_json"]:
                return jsonify(error="This run is still being checked. Please wait or retry with a new request."), 409
            cached = _decode_json(row["response_json"], {})
            code = int(cached.pop("_http_status", 200))
            return jsonify(cached), code
        finally:
            conn.close()

    def reserve_request(uid, operation, payload, runs):
        data = get_json()
        request_id = str(data.get("request_id") or "").strip()[:100] or str(uuid.uuid4())
        digest = _fingerprint(payload)
        now = _utc_now()
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            lock_execution_counter(cursor)
            cursor.execute("SELECT * FROM execution_requests WHERE request_id=?", (request_id,))
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                if int(existing["user_id"]) != uid or existing["operation"] != operation or existing["payload_hash"] != digest:
                    return request_id, (jsonify(error="This request ID was already used for a different action."), 409), False
                if existing["response_json"]:
                    cached = _decode_json(existing["response_json"], {})
                    code = int(cached.pop("_http_status", 200))
                    return request_id, (jsonify(cached), code), False
                return request_id, (jsonify(error="This run is still being checked. Please wait or retry with a new request."), 409), False

            hour_limit, day_limit, month_limit = quota_limits()
            hour_start = _iso(now - timedelta(hours=1))
            day_start = _iso(now - timedelta(days=1))
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            windows = (_iso(month_start), hour_start, day_start)
            if runs:
                cursor.execute(
                    "SELECT COALESCE(SUM(runs),0) AS n FROM execution_requests WHERE status IN ('pending','complete') AND created_at>=?",
                    (windows[0],),
                )
                monthly = int(cursor.fetchone()["n"])
                cursor.execute(
                    "SELECT COALESCE(SUM(runs),0) AS n FROM execution_requests WHERE user_id=? AND status IN ('pending','complete') AND created_at>=?",
                    (uid, windows[1]),
                )
                hourly = int(cursor.fetchone()["n"])
                cursor.execute(
                    "SELECT COALESCE(SUM(runs),0) AS n FROM execution_requests WHERE user_id=? AND status IN ('pending','complete') AND created_at>=?",
                    (uid, windows[2]),
                )
                daily = int(cursor.fetchone()["n"])
                if hourly >= hour_limit:
                    conn.rollback()
                    return request_id, (jsonify(error="Hourly code-run limit reached. Try again later."), 429), False
                if daily >= day_limit:
                    conn.rollback()
                    return request_id, (jsonify(error="Daily code-run limit reached. Try again tomorrow."), 429), False
                if monthly >= month_limit:
                    conn.rollback()
                    return request_id, (jsonify(error="Monthly code-run limit reached."), 429), False
            cursor.execute(
                """INSERT INTO execution_requests
                   (request_id,user_id,operation,payload_hash,status,runs,created_at,response_json)
                   VALUES (?,?,?,?, 'pending', ?, ?, NULL)""",
                (request_id, uid, operation, digest, runs, _iso(now)),
            )
            conn.commit()
            return request_id, None, True
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not reserve a code run")
            return request_id, (jsonify(error="Could not prepare this run. Please retry."), 503), False
        finally:
            conn.close()

    def save_request_response(request_id, response, status_code=200, *, ran=False):
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            lock_execution_counter(cursor)
            cursor.execute(
                "UPDATE execution_requests SET status=?,runs=?,response_json=? WHERE request_id=? AND status='pending'",
                ("complete" if ran or status_code < 500 else "failed", 1 if ran else 0,
                 json.dumps({**response, "_http_status": int(status_code)}), request_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not save code run response")
            raise
        finally:
            conn.close()

    def active_question(uid, data):
        course_id = str(data.get("course_id") or "").strip()
        level = str(data.get("level") or "").lower()
        try:
            number = int(data.get("question_number"))
        except (ValueError, TypeError):
            return None, None, None, (jsonify(error="Invalid question number"), 400)
        if not course_id or level not in LEVELS or number not in range(1, 6):
            return None, None, None, (jsonify(error="Invalid course, difficulty, or question number."), 400)
        conn = get_db()
        try:
            cursor = conn.cursor()
            progress = latest_progress(cursor, uid, course_id)
            if not progress or progress["current_level"] != level or int(progress["current_question_number"]) != number:
                return None, None, None, (jsonify(error="Your saved question changed. Reload the game to continue."), 409)
            attempt = latest_attempt(cursor, progress["id"], level)
            if not attempt or attempt["status"] != "active":
                return None, None, None, (jsonify(error="This difficulty attempt has ended. Retry the difficulty to continue."), 409)
            questions = _decode_json(progress["session_questions"], {})
            chosen = questions.get(level, [])[number - 1]
            variant = int(chosen["alt"])
            if variant not in (1, 2, 3):
                return None, None, None, (jsonify(error="Saved question variant is invalid."), 409)
            if ("question_id" in data and str(data["question_id"]) != str(chosen["id"])) or (
                    "question_alt" in data and str(data["question_alt"]) != str(variant)):
                return None, None, None, (jsonify(error="Your saved question changed. Reload the game to continue."), 409)
            cursor.execute(
                "SELECT * FROM questions WHERE course_id=? AND level=? AND id=?",
                (course_id, level, chosen["id"]),
            )
            question = cursor.fetchone()
            if not question or question[f"question_text_{variant}"] != chosen["question_text"]:
                return None, None, None, (jsonify(error="The saved question bank changed. Start a new journey."), 409)
            expected = question[f"expected_output_{variant}"]
            if not expected:
                return None, None, None, (jsonify(error="Question grading data is unavailable."), 503)
            return {"course_id": course_id, "level": level, "number": number, "progress_id": progress["id"],
                    "attempt_id": attempt["id"], "question_id": str(chosen["id"]), "question_alt": variant,
                    "language": question["language"], "expected": expected}, progress, attempt, None
        except (KeyError, IndexError, TypeError, ValueError):
            return None, None, None, (jsonify(error="Saved question data is damaged. Restart this course."), 409)
        finally:
            conn.close()

    def is_html(language):
        return (language or "").strip().casefold() in ("html and css", "html/css")

    def provider_json_error(exc):
        body = {"error": str(exc), "provider_error": True, "error_type": "provider_error"}
        headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
        return jsonify(body), exc.status, headers

    def run_code_endpoint():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        data = get_json()
        code = data.get("code", "")
        stdin = data.get("input", "")
        if not isinstance(code, str) or not code.strip():
            return jsonify(error="Write some code before running it."), 400
        if len(code.encode("utf-8")) > 20_000:
            return jsonify(error="Code is too long (20 KB maximum)."), 413
        if not isinstance(stdin, str) or len(stdin.encode("utf-8")) > 16_000:
            return jsonify(error="Input is too long (16 KB maximum)."), 413
        try:
            replay_course = str(data.get("course_id") or "").strip()
            replay_level = str(data.get("level") or "").lower()
            replay_number = int(data.get("question_number"))
        except (ValueError, TypeError):
            replay_course, replay_level, replay_number = "", "", 0
        replay_payload = {"course_id": replay_course, "level": replay_level, "number": replay_number,
                          "code": code, "input": stdin, "mode": "run"}
        replay = replay_request(uid, "run_code", replay_payload)
        if replay is not None:
            return replay
        question, progress, attempt, invalid = active_question(uid, data)
        if invalid:
            return invalid
        if is_html(question["language"]):
            return jsonify(output="HTML and CSS are validated when you submit this answer.", error=None, ran=False)
        payload = {"course_id": question["course_id"], "level": question["level"], "number": question["number"],
                   "code": code, "input": stdin, "mode": "run"}
        request_id, rejection, reserved = reserve_request(uid, "run_code", payload, 1)
        if rejection:
            return rejection
        try:
            result = execute_code(code, question["language"], stdin)
        except ProviderFailure as exc:
            response, status, headers = provider_json_error(exc)
            save_request_response(request_id, response.get_json(), status, ran=False)
            return response, status, headers
        except ValueError as exc:
            body = {"error": str(exc), "provider_error": False, "error_type": "invalid_code"}
            save_request_response(request_id, body, 400, ran=False)
            return jsonify(body), 400
        body = {"output": result.output, "error": result.error, "error_type": result.error_type,
                "ran": result.ran, "execution_time": result.execution_time}
        save_request_response(request_id, body, 200, ran=result.ran)
        return jsonify(body)

    def attempt_submission(uid, question, code, stdin, operation, request_id):
        from evaluator import compare_outputs as default_compare
        from html_evaluator import evaluate_html as default_html_evaluator
        compare = compare_outputs or default_compare
        validate_html = evaluate_html or default_html_evaluator

        if is_html(question["language"]):
            outcome = validate_html(code, question["expected"])
            correct = bool(outcome.is_correct and outcome.rules_total > 0)
            output = "HTML/CSS structure validated." if correct else "HTML/CSS structure does not match the task."
            execution_error = None
            execution_type = None
            ran = False
        else:
            try:
                result = execute_code(code, question["language"], stdin)
            except ProviderFailure as exc:
                body = {"error": str(exc), "provider_error": True, "error_type": "provider_error"}
                save_request_response(request_id, body, exc.status, ran=False)
                return jsonify(body), exc.status, ({"Retry-After": exc.retry_after} if exc.retry_after else None)
            except ValueError as exc:
                body = {"error": str(exc), "provider_error": False, "error_type": "invalid_code"}
                save_request_response(request_id, body, 400, ran=False)
                return jsonify(body), 400
            output = result.output or ""
            execution_error = result.error
            execution_type = result.error_type
            ran = bool(result.ran)
            correct = False if execution_error or execution_type else bool(compare(output, question["expected"], mode="normalized").is_correct)

        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            lock_execution_counter(cursor)
            cursor.execute("SELECT * FROM execution_requests WHERE request_id=?", (request_id,))
            request_row = cursor.fetchone()
            if not request_row or request_row["status"] != "pending":
                conn.rollback()
                return jsonify(error="This answer was already checked. Reload the game."), 409
            cursor.execute("SELECT * FROM progress WHERE id=? AND user_id=? AND completed=0", (question["progress_id"], uid))
            progress = cursor.fetchone()
            cursor.execute("SELECT * FROM difficulty_attempts WHERE id=? AND progress_id=?", (question["attempt_id"], question["progress_id"]))
            attempt = cursor.fetchone()
            saved = _decode_json(progress["session_questions"], {}) if progress else {}
            selected = saved.get(question["level"], []) if isinstance(saved, dict) else []
            chosen = selected[question["number"] - 1] if len(selected) >= question["number"] else {}
            if (not progress or not attempt or attempt["status"] != "active"
                    or progress["current_level"] != question["level"]
                    or int(progress["current_question_number"]) != question["number"]
                    or str(chosen.get("id")) != question["question_id"]
                    or str(chosen.get("alt")) != str(question["question_alt"])):
                conn.rollback()
                body = {"error": "Your saved question changed. Reload the game to continue."}
                save_request_response(request_id, body, 409, ran=ran)
                return jsonify(body), 409

            total = int(attempt["bounty_earned"] or 0)
            if correct:
                reward = REWARDS[question["level"]]
                next_level, next_number = question["level"], question["number"] + 1
                completes_difficulty = question["number"] == 5
                completes_course = completes_difficulty and question["level"] == "hard"
                if completes_difficulty and not completes_course:
                    next_level = LEVELS[LEVELS.index(question["level"]) + 1]
                    next_number = 1
                elif completes_course:
                    next_number = 5
                cursor.execute(
                    """UPDATE progress SET current_level=?,current_question_number=?,completed=?,
                       bounty_earned=bounty_earned+?,last_updated=CURRENT_TIMESTAMP
                       WHERE id=? AND user_id=? AND completed=0 AND current_level=? AND current_question_number=?""",
                    (next_level, next_number, int(completes_course), reward, progress["id"], uid, question["level"], question["number"]),
                )
                if cursor.rowcount != 1:
                    conn.rollback()
                    body = {"error": "This question was already completed. Reload the game."}
                    save_request_response(request_id, body, 409, ran=ran)
                    return jsonify(body), 409
                cursor.execute("UPDATE users SET total_bounty=total_bounty+? WHERE id=?", (reward, uid))
                if completes_difficulty:
                    final_bounty = total + reward
                    cursor.execute(
                        "UPDATE difficulty_attempts SET status='completed',hearts_remaining=?,bounty_earned=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='active'",
                        (attempt["hearts_remaining"], final_bounty, attempt["id"]),
                    )
                    cursor.execute(
                        """INSERT INTO difficulty_best(user_id,difficulty,bounty,course_id,completed_at)
                           VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                           ON CONFLICT(user_id,difficulty) DO UPDATE SET
                             bounty=CASE WHEN excluded.bounty>difficulty_best.bounty THEN excluded.bounty ELSE difficulty_best.bounty END,
                             course_id=CASE WHEN excluded.bounty>difficulty_best.bounty THEN excluded.course_id ELSE difficulty_best.course_id END,
                             completed_at=CASE WHEN excluded.bounty>difficulty_best.bounty THEN excluded.completed_at ELSE difficulty_best.completed_at END""",
                        (uid, question["level"], final_bounty, question["course_id"]),
                    )
                    if not completes_course:
                        cursor.execute(
                            """INSERT INTO difficulty_attempts
                               (progress_id,user_id,course_id,difficulty,attempt_number,hearts_remaining,bounty_earned,status)
                               VALUES (?,?,?, ?,1,?,0,'active')""",
                            (progress["id"], uid, question["course_id"], next_level, STARTING_HEARTS),
                        )
                else:
                    cursor.execute(
                        "UPDATE difficulty_attempts SET bounty_earned=bounty_earned+? WHERE id=? AND status='active'",
                        (reward, attempt["id"]),
                    )
                cursor.execute("SELECT total_bounty FROM users WHERE id=?", (uid,))
                user = cursor.fetchone()
                if completes_course:
                    cursor.execute("SELECT name FROM courses WHERE id=?", (question["course_id"],))
                    course = cursor.fetchone()
                    cursor.execute("SELECT bounty_earned FROM progress WHERE id=?", (progress["id"],))
                    course_progress = cursor.fetchone()
                    cursor.execute(
                        "INSERT INTO bounty_records(user_id,course_id,course_name,bounty) VALUES (?,?,?,?)",
                        (uid, question["course_id"], course["name"] if course else question["course_id"], course_progress["bounty_earned"]),
                    )
                body = {
                    "correct": True, "output": output.strip()[:4000], "error": None,
                    "error_type": None, "completed": completes_course,
                    "difficulty_completed": completes_difficulty, "next_level": next_level,
                    "next_question_number": next_number, "bounty_gained": reward,
                    "difficulty_bounty": (final_bounty if completes_difficulty else total + reward),
                    "hearts_remaining": STARTING_HEARTS if completes_difficulty and not completes_course else int(attempt["hearts_remaining"]),
                    "total_bounty": int(user["total_bounty"]),
                    "success_message": "Correct! The answer has been saved.",
                }
            else:
                hearts = max(0, int(attempt["hearts_remaining"]) - 1)
                after_penalty = max(0, total - WRONG_ANSWER_PENALTY)
                reset_amount = after_penalty if hearts == 0 else 0
                updated_attempt_bounty = 0 if hearts == 0 else after_penalty
                next_number = 1 if hearts == 0 else question["number"]
                cursor.execute(
                    "UPDATE difficulty_attempts SET hearts_remaining=?,bounty_earned=?,status=?,completed_at=CASE WHEN ?=0 THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id=? AND status='active'",
                    (hearts, updated_attempt_bounty, "failed" if hearts == 0 else "active", hearts, attempt["id"]),
                )
                cursor.execute(
                    "UPDATE progress SET current_question_number=?,bounty_earned=CASE WHEN bounty_earned>=? THEN bounty_earned-? ELSE 0 END,last_updated=CURRENT_TIMESTAMP WHERE id=?",
                    (next_number, WRONG_ANSWER_PENALTY + reset_amount, WRONG_ANSWER_PENALTY + reset_amount, progress["id"]),
                )
                cursor.execute(
                    "UPDATE users SET total_bounty=CASE WHEN total_bounty>=? THEN total_bounty-? ELSE 0 END WHERE id=?",
                    (WRONG_ANSWER_PENALTY + reset_amount, WRONG_ANSWER_PENALTY + reset_amount, uid),
                )
                cursor.execute("SELECT total_bounty FROM users WHERE id=?", (uid,))
                user = cursor.fetchone()
                body = {
                    "correct": False, "output": output.strip()[:4000],
                    "error": (execution_error or "")[:4000] or None,
                    "error_type": execution_type or "wrong_output",
                    "comparison_detail": "The output did not match the task." if not execution_error else None,
                    "hearts_remaining": hearts, "attempt_failed": hearts == 0,
                    "difficulty_bounty": 0 if hearts == 0 else after_penalty,
                    "bounty_lost": WRONG_ANSWER_PENALTY + reset_amount,
                    "total_bounty": int(user["total_bounty"]),
                    "current_question_number": next_number,
                }
            cursor.execute(
                "UPDATE execution_requests SET status='complete',runs=?,response_json=? WHERE request_id=? AND status='pending'",
                (1 if ran else 0, json.dumps({**body, "_http_status": 200}), request_id),
            )
            conn.commit()
            return jsonify(body), 200
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not save answer result")
            save_request_response(request_id, {"error": "Could not save this answer. Please reload before retrying."}, 503, ran=ran)
            return jsonify(error="Could not save this answer. Please reload before retrying."), 503
        finally:
            conn.close()

    def submit_answer():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        data = get_json()
        code = data.get("code", "")
        stdin = data.get("input", "")
        if not isinstance(code, str) or not code.strip():
            return jsonify(error="Write some code before submitting."), 400
        if len(code.encode("utf-8")) > 20_000:
            return jsonify(error="Code is too long (20 KB maximum)."), 413
        if not isinstance(stdin, str) or len(stdin.encode("utf-8")) > 16_000:
            return jsonify(error="Input is too long (16 KB maximum)."), 413
        try:
            replay_course = str(data.get("course_id") or "").strip()
            replay_level = str(data.get("level") or "").lower()
            replay_number = int(data.get("question_number"))
        except (ValueError, TypeError):
            replay_course, replay_level, replay_number = "", "", 0
        replay_payload = {"course_id": replay_course, "level": replay_level, "number": replay_number,
                          "code": code, "input": stdin, "mode": "submit"}
        replay = replay_request(uid, "submit_answer", replay_payload)
        if replay is not None:
            return replay
        question, progress, attempt, invalid = active_question(uid, data)
        if invalid:
            return invalid
        payload = {"course_id": question["course_id"], "level": question["level"], "number": question["number"],
                   "code": code, "input": stdin, "mode": "submit"}
        request_id, rejection, reserved = reserve_request(uid, "submit_answer", payload, 0 if is_html(question["language"]) else 1)
        if rejection:
            return rejection
        return attempt_submission(uid, question, code, stdin, "submit_answer", request_id)

    def retry_difficulty():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        course_id = str(get_json().get("course_id") or "").strip()
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            lock_execution_counter(cursor)
            progress = latest_progress(cursor, uid, course_id)
            if not progress:
                conn.rollback()
                return jsonify(error="No active course attempt was found."), 404
            attempt = latest_attempt(cursor, progress["id"], progress["current_level"])
            if not attempt or attempt["status"] != "failed":
                conn.rollback()
                return jsonify(error="This difficulty has not failed."), 409
            cursor.execute(
                "SELECT COALESCE(MAX(attempt_number),0)+1 AS next_attempt FROM difficulty_attempts WHERE progress_id=? AND difficulty=?",
                (progress["id"], progress["current_level"]),
            )
            number = int(cursor.fetchone()["next_attempt"])
            cursor.execute(
                """INSERT INTO difficulty_attempts
                   (progress_id,user_id,course_id,difficulty,attempt_number,hearts_remaining,bounty_earned,status)
                   VALUES (?,?,?,?,?,?,0,'active')""",
                (progress["id"], uid, course_id, progress["current_level"], number, STARTING_HEARTS),
            )
            saved = _decode_json(progress["session_questions"], {})
            level = progress["current_level"]
            saved[level] = sample_difficulty(cursor, course_id, level, saved.get(level, []))
            cursor.execute("UPDATE progress SET current_question_number=1,session_questions=?,last_updated=CURRENT_TIMESTAMP WHERE id=?",
                           (json.dumps(saved), progress["id"]))
            cursor.execute("SELECT * FROM progress WHERE id=?", (progress["id"],))
            progress = cursor.fetchone()
            state = game_state(cursor, progress, uid, course_id)
            conn.commit()
            return jsonify(success=True, session_questions=public_session(saved), **state)
        except Exception:
            conn.rollback()
            logging.getLogger(__name__).exception("Could not retry difficulty")
            return jsonify(error="Could not start a new difficulty attempt. Please retry."), 500
        finally:
            conn.close()

    def get_game_state():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        course_id = str(request.args.get("course_id") or "").strip()
        conn = get_db()
        try:
            cursor = conn.cursor()
            progress = latest_progress(cursor, uid, course_id)
            if not progress:
                return jsonify(error="No active course attempt was found."), 404
            state = game_state(cursor, progress, uid, course_id)
            conn.commit()
            return jsonify(**state)
        finally:
            conn.close()

    def complete_course():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        course_id = str(get_json().get("course_id") or "").strip()
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM progress WHERE user_id=? AND course_id=? AND completed=1 ORDER BY id DESC LIMIT 1", (uid, course_id))
            if cursor.fetchone():
                return jsonify(success=True, completed=True)
            return jsonify(error="Finish all 15 questions before completing the course."), 409
        finally:
            conn.close()

    def leaderboard_data():
        uid, error_response = user_id_or_response()
        if error_response:
            return error_response
        difficulty = str(request.args.get("difficulty") or "overall").casefold()
        if difficulty not in ("overall", *LEVELS):
            return jsonify(error="Choose overall, easy, medium, or hard."), 400
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.id,COALESCE(NULLIF(p.display_name,''),u.username) AS display_name,
                   COALESCE(MAX(CASE WHEN b.difficulty='easy' THEN b.bounty END),0) AS easy_bounty,
                   COALESCE(MAX(CASE WHEN b.difficulty='medium' THEN b.bounty END),0) AS medium_bounty,
                   COALESCE(MAX(CASE WHEN b.difficulty='hard' THEN b.bounty END),0) AS hard_bounty,
                   COUNT(b.difficulty) AS completed_difficulties
                   FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
                   LEFT JOIN difficulty_best b ON b.user_id=u.id
                   GROUP BY u.id,u.username,p.display_name
                   HAVING COUNT(b.difficulty)>0"""
            )
            rows = []
            for row in cursor.fetchall():
                item = {"user_id": int(row["id"]), "display_name": row["display_name"],
                        "easy": int(row["easy_bounty"]), "medium": int(row["medium_bounty"]),
                        "hard": int(row["hard_bounty"])}
                item["overall"] = item["easy"] + item["medium"] + item["hard"]
                item["score"] = item[difficulty]
                rows.append(item)
            rows.sort(key=lambda item: (-item["score"], item["display_name"].casefold(), item["user_id"]))
            public_rows = [{"rank": index + 1, "display_name": item["display_name"], "bounty": item["score"],
                            "user": item["user_id"] == uid} for index, item in enumerate(rows[:100])]
            return jsonify(difficulty=difficulty, entries=public_rows, current_user=next((row for row in public_rows if row["user"]), None))
        finally:
            conn.close()

    def leaderboard_page():
        uid, error_response = user_id_or_response()
        if error_response:
            return __import__("flask").redirect("/login")
        return render_template("leaderboard.html", username=session.get("username", ""))

    def retired_lose_heart():
        return jsonify(error="Hearts and penalties are applied only by answer submissions."), 410

    app.add_url_rule("/api/start_session", "api_start_session", start_session, methods=["POST"])
    app.add_url_rule("/api/get_questions", "api_get_questions", rotate_question, methods=["POST"])
    app.add_url_rule("/api/submit_answer", "api_submit_answer", submit_answer, methods=["POST"])
    app.add_url_rule("/api/complete_course", "api_complete_course", complete_course, methods=["POST"])
    app.add_url_rule("/api/lose_heart", "api_lose_heart", retired_lose_heart, methods=["POST"])
    app.add_url_rule("/api/run_code", "api_run_code", run_code_endpoint, methods=["POST"])
    app.add_url_rule("/api/retry_difficulty", "api_retry_difficulty", retry_difficulty, methods=["POST"])
    app.add_url_rule("/api/game_state", "api_game_state", get_game_state, methods=["GET"])
    app.add_url_rule("/api/leaderboard", "api_leaderboard", leaderboard_data, methods=["GET"])
    app.add_url_rule("/leaderboard", "leaderboard", leaderboard_page, methods=["GET"])
