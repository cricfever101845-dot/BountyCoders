"""BountyCoders question rotation and server-authoritative answer checking.

Generated companion module for the college project. Keeps the existing DB schema.
Run through app.py after installing with install_bountycoders_upgrade.py.
"""
import json
import os
import sqlite3
from flask import jsonify, request, session

LEVELS = ('easy', 'medium', 'hard')
REWARDS = {'easy': 5_000_000, 'medium': 10_000_000, 'hard': 15_000_000}


def install(app, get_db, run_code, compare_outputs, classify_error, evaluate_html):
    """Install improved route implementations without editing unrelated app code."""
    from bounty_runner import run_student_code

    conn = get_db()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS question_rotation (
            user_id INTEGER NOT NULL, course_id TEXT NOT NULL,
            level TEXT NOT NULL, question_number INTEGER NOT NULL,
            last_alt INTEGER NOT NULL CHECK (last_alt BETWEEN 1 AND 3),
            PRIMARY KEY (user_id, course_id, level, question_number)
        )''')
        conn.commit()
    finally:
        conn.close()

    def get_json():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def public_session(questions):
        # Expected outputs never leave the server.
        return {level: [
            {k: q[k] for k in ('id', 'question_text', 'opponent_name', 'language', 'alt') if k in q}
            for q in questions.get(level, [])
        ] for level in LEVELS}

    def next_variant(c, user_id, course_id, level, question_number):
        c.execute('''SELECT last_alt FROM question_rotation
            WHERE user_id=? AND course_id=? AND level=? AND question_number=?''',
            (user_id, course_id, level, question_number))
        row = c.fetchone()
        # First playthrough spreads variants across the five islands.
        choice = (int(row['last_alt']) % 3) + 1 if row else \
                 ((question_number - 1 + LEVELS.index(level)) % 3) + 1
        c.execute('''INSERT INTO question_rotation
            (user_id, course_id, level, question_number, last_alt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, course_id, level, question_number)
            DO UPDATE SET last_alt=excluded.last_alt''',
            (user_id, course_id, level, question_number, choice))
        return choice

    def make_question(row, alt):
        if alt not in (1, 2, 3):
            raise ValueError('Invalid question variant')
        qtext = row[f'question_text_{alt}']
        if not qtext:
            raise ValueError('An alternative question is empty')
        return {'id': row['id'], 'question_text': qtext,
                'opponent_name': row['opponent_name'], 'language': row['language'],
                'alt': alt}

    def incomplete_progress(c, user_id, course_id):
        c.execute('''SELECT * FROM progress
            WHERE user_id=? AND course_id=? AND completed=0
            ORDER BY id DESC LIMIT 1''', (user_id, course_id))
        return c.fetchone()

    def start_session():
        if 'user_id' not in session:
            return jsonify(error='Not logged in'), 401
        data = get_json()
        course_id = str(data.get('course_id') or '').strip()
        force_new = data.get('force_new') is True
        if not course_id:
            return jsonify(error='Missing course ID'), 400
        user_id = int(session['user_id'])
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('BEGIN IMMEDIATE')
            c.execute('SELECT id FROM courses WHERE id=?', (course_id,))
            if not c.fetchone():
                return jsonify(error='Course not found'), 404
            existing = incomplete_progress(c, user_id, course_id)
            if existing is not None and not force_new:
                try:
                    questions = json.loads(existing['session_questions'] or '{}')
                except (ValueError, TypeError):
                    questions = {}
                if all(len(questions.get(level, [])) == 5 for level in LEVELS):
                    return jsonify(resumed=True,
                        current_level=existing['current_level'],
                        current_question_number=existing['current_question_number'],
                        bounty_earned=existing['bounty_earned'],
                        session_questions=public_session(questions))
                return jsonify(error='Saved question session is damaged. Start a new journey.'), 409

            all_questions = {}
            for level in LEVELS:
                c.execute('''SELECT * FROM questions
                    WHERE course_id=? AND level=? ORDER BY question_number''',
                    (course_id, level))
                rows = c.fetchall()
                if len(rows) != 5 or [int(r['question_number']) for r in rows] != [1,2,3,4,5]:
                    return jsonify(error=f'Question bank for {level} must contain exactly five question groups.'), 500
                level_questions = []
                for row in rows:
                    number = int(row['question_number'])
                    alt = next_variant(c, user_id, course_id, level, number)
                    level_questions.append(make_question(row, alt))
                all_questions[level] = level_questions

            c.execute('DELETE FROM progress WHERE user_id=? AND course_id=? AND completed=0',
                      (user_id, course_id))
            c.execute('''INSERT INTO progress
                (user_id, course_id, current_level, current_question_number,
                 completed, session_questions, bounty_earned)
                VALUES (?, ?, 'easy', 1, 0, ?, 0)''',
                (user_id, course_id, json.dumps(all_questions)))
            conn.commit()
            return jsonify(resumed=False, current_level='easy',
                current_question_number=1, bounty_earned=0,
                session_questions=public_session(all_questions))
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            return jsonify(error=f'Could not start course: {exc}'), 500
        finally:
            conn.close()

    def rotate_question():
        """Rotate only the active question, persist it for grading and resuming."""
        if 'user_id' not in session:
            return jsonify(error='Not logged in'), 401
        data = get_json()
        course_id = str(data.get('course_id') or '').strip()
        level = str(data.get('level') or '').lower()
        try:
            number = int(data.get('question_number'))
        except (ValueError, TypeError):
            return jsonify(error='Invalid question number'), 400
        if level not in LEVELS or not 1 <= number <= 5:
            return jsonify(error='Invalid level or question number'), 400
        user_id = int(session['user_id'])
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('BEGIN IMMEDIATE')
            prog = incomplete_progress(c, user_id, course_id)
            if not prog or prog['current_level'] != level or int(prog['current_question_number']) != number:
                return jsonify(error='You can only retry your active question.'), 409
            stored = json.loads(prog['session_questions'] or '{}')
            c.execute('''SELECT * FROM questions WHERE course_id=? AND level=? AND question_number=?''',
                      (course_id, level, number))
            question = c.fetchone()
            if not question:
                return jsonify(error='Question not found'), 404
            alt = next_variant(c, user_id, course_id, level, number)
            entry = make_question(question, alt)
            stored[level][number - 1] = entry
            c.execute('UPDATE progress SET session_questions=?,last_updated=CURRENT_TIMESTAMP WHERE id=?',
                      (json.dumps(stored), prog['id']))
            conn.commit()
            return jsonify(question=entry, success=True)
        except (sqlite3.Error, ValueError, KeyError, TypeError, IndexError) as exc:
            return jsonify(error=f'Could not rotate question: {exc}'), 500
        finally:
            conn.close()

    def submit_answer():
        if 'user_id' not in session:
            return jsonify(error='Not logged in'), 401
        data = get_json()
        course_id = str(data.get('course_id') or '').strip()
        level = str(data.get('level') or '').lower()
        code = data.get('code', '')
        try:
            number = int(data.get('question_number'))
        except (ValueError, TypeError):
            return jsonify(error='Invalid question number'), 400
        if level not in LEVELS or number not in (1, 2, 3, 4, 5):
            return jsonify(error='Invalid level or question number'), 400
        if not isinstance(code, str) or not code.strip():
            return jsonify(error='Write some code before submitting.'), 400
        if len(code.encode('utf-8')) > 20_000:
            return jsonify(error='Code is too long (20 KB maximum).'), 413
        user_id = int(session['user_id'])
        conn = get_db()
        try:
            c = conn.cursor()
            prog = incomplete_progress(c, user_id, course_id)
            if not prog or prog['current_level'] != level or int(prog['current_question_number']) != number:
                return jsonify(error='Your question changed. Reload the game to continue.'), 409
            try:
                stored = json.loads(prog['session_questions'] or '{}')
                chosen = stored[level][number-1]
                alt = int(chosen['alt'])
                if alt not in (1,2,3):
                    raise ValueError('Invalid variant')
            except (ValueError, TypeError, KeyError, IndexError):
                return jsonify(error='Saved question is missing. Start a new journey.'), 409
            c.execute('SELECT * FROM questions WHERE course_id=? AND level=? AND question_number=?',
                      (course_id, level, number))
            question = c.fetchone()
            if not question or str(question['id']) != str(chosen['id']):
                return jsonify(error='Your question bank changed. Restart this course.'), 409
            expected = question[f'expected_output_{alt}']
            language = question['language']
            progress_id = prog['id']
            if not expected or not language:
                return jsonify(error='Question lacks grading data.'), 500
        finally:
            conn.close()

        # Docker is the default; host execution requires explicit, trusted-local opt-in.
        result = run_student_code(code, language, run_code)
        output = str(result.get('output') or '')[:4000]
        if result.get('error'):
            typ = result.get('error_type') or classify_error(result)
            return jsonify(correct=False, output=output, error=str(result['error'])[:4000],
                           error_type=typ)
        if language.lower() in ('html and css', 'html/css'):
            outcome = evaluate_html(code, expected)
            correct = outcome.is_correct and outcome.rules_total > 0
            detail = outcome.detail if outcome.rules_total > 0 else 'Invalid HTML grading rules in the question bank.'
        else:
            outcome = compare_outputs(output, expected, mode='normalized')
            correct = outcome.is_correct
            detail = outcome.detail
        if not correct:
            return jsonify(correct=False, output=output.strip(), error=None,
                error_type='wrong_output', comparison_detail=str(detail or 'Output did not match the task.')[:4000])

        next_level = level
        next_num = number + 1
        completed = level == 'hard' and number == 5
        if number == 5 and not completed:
            next_level = LEVELS[LEVELS.index(level)+1]
            next_num = 1
        elif completed:
            next_num = 5
        bounty_gain = REWARDS[level]
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('BEGIN IMMEDIATE')
            # Compare-and-set prevents accidental double bounty from repeated clicks.
            c.execute('''UPDATE progress SET current_level=?,current_question_number=?,
                completed=?,bounty_earned=bounty_earned+?,last_updated=CURRENT_TIMESTAMP
                WHERE id=? AND user_id=? AND course_id=? AND current_level=?
                AND current_question_number=? AND completed=0''',
                (next_level, next_num, int(completed), bounty_gain,
                 progress_id, user_id, course_id, level, number))
            if c.rowcount != 1:
                return jsonify(error='This question has already been completed. Reload your game.'), 409
            c.execute('UPDATE users SET total_bounty=total_bounty+? WHERE id=?',
                      (bounty_gain, user_id))
            if completed:
                c.execute('SELECT name FROM courses WHERE id=?', (course_id,))
                course = c.fetchone()
                c.execute('SELECT bounty_earned FROM progress WHERE id=?', (progress_id,))
                last = c.fetchone()
                c.execute('''INSERT INTO bounty_records (user_id, course_id, course_name, bounty)
                    VALUES (?, ?, ?, ?)''',
                    (user_id, course_id, course['name'] if course else course_id, last['bounty_earned']))
            conn.commit()
            session['bounty_updated'] = True
            msg = 'HTML structure validated! Next island unlocked.' if language.lower() in ('html and css','html/css') else 'Code executed successfully! Next island unlocked.'
            return jsonify(correct=True, output=output.strip()[:4000], error=None,
                error_type=None, success_message=msg, completed=completed,
                next_level=next_level, next_question_number=next_num,
                bounty_gained=bounty_gain)
        finally:
            conn.close()

    def complete_course():
        if 'user_id' not in session:
            return jsonify(error='Not logged in'), 401
        course_id = str(get_json().get('course_id') or '').strip()
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('''SELECT id FROM progress WHERE user_id=? AND course_id=? AND completed=1
                ORDER BY id DESC LIMIT 1''', (int(session['user_id']), course_id))
            if c.fetchone():
                return jsonify(success=True, completed=True)
            return jsonify(error='Finish all 15 questions before completing the course.'), 409
        finally:
            conn.close()

    # Replace the Flask endpoints; preserve original function names in app.py.
    app.view_functions['api_start_session'] = start_session
    app.view_functions['api_get_questions'] = rotate_question
    app.view_functions['api_submit_answer'] = submit_answer
    app.view_functions['api_complete_course'] = complete_course
