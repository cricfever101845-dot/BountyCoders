from flask import Flask, Response, current_app, g, has_app_context, render_template, request, redirect, session, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import subprocess
import sys
import os
import json
import random
import re
import tempfile
import shutil
import logging
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UpstreamRequest, urlopen

from database import connect_db, initialize_database, is_postgres_enabled

# Central output evaluation engine
from evaluator import compare_outputs, classify_error
# HTML structural validator
from html_evaluator import evaluate_html

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development').strip().lower()
SERVICE_ROLE = os.environ.get('SERVICE_ROLE', 'frontend').strip().lower()
AVATAR_NAMES = {
    name.casefold(): name for name in (
        'luffy', 'roronoa zoro', 'nami', 'SANJI', 'ace', 'trafalgar law',
        'brook', 'franky', 'robin', 'god ussop', 'doflamingo',
    )
}
configured_secret = os.environ.get('BOUNTY_SECRET_KEY') or os.environ.get('SECRET_KEY')
if ENVIRONMENT == 'production' and not configured_secret:
    raise RuntimeError('BOUNTY_SECRET_KEY is required when ENVIRONMENT=production.')
if ENVIRONMENT == 'production' and not os.environ.get('DATABASE_URL'):
    raise RuntimeError('DATABASE_URL is required when ENVIRONMENT=production.')
if ENVIRONMENT == 'production' and SERVICE_ROLE not in ('frontend', 'backend'):
    raise RuntimeError('SERVICE_ROLE must be frontend or backend in production.')
if ENVIRONMENT == 'production' and SERVICE_ROLE == 'frontend' and not os.environ.get('BACKEND_URL'):
    raise RuntimeError('BACKEND_URL is required on the frontend service.')
if ENVIRONMENT == 'production' and SERVICE_ROLE == 'backend' and not os.environ.get('FRONTEND_URL'):
    raise RuntimeError('FRONTEND_URL is required on the backend service.')
if ENVIRONMENT == 'production' and SERVICE_ROLE == 'frontend' and urlsplit(os.environ.get('BACKEND_URL', '')).scheme.lower() != 'https':
    raise RuntimeError('BACKEND_URL must use HTTPS in production.')
if ENVIRONMENT == 'production' and SERVICE_ROLE == 'backend' and urlsplit(os.environ.get('FRONTEND_URL', '')).scheme.lower() != 'https':
    raise RuntimeError('FRONTEND_URL must use HTTPS in production.')

app.secret_key = configured_secret or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=(ENVIRONMENT == 'production'),
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=64 * 1024,
)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


def _origin(value):
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    return f'{parsed.scheme.lower()}://{parsed.netloc.lower()}'


def _allowed_frontend_origins():
    origins = set()
    configured = os.environ.get('FRONTEND_URL', '')
    if configured:
        origin = _origin(configured)
        if origin:
            origins.add(origin)
    external_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
    if external_host:
        origins.add('https://' + external_host.lower())
    return origins


def normalize_avatar(value):
    return AVATAR_NAMES.get(value.strip().casefold(), 'luffy') if isinstance(value, str) else 'luffy'


@app.before_request
def deployment_request_guard():
    if ENVIRONMENT == 'production' and SERVICE_ROLE == 'backend' and request.path not in ('/health', '/ready') and not request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404

    if ENVIRONMENT == 'production' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = _origin(request.headers.get('Origin'))
        allowed = _allowed_frontend_origins()
        if origin and allowed and origin not in allowed:
            return jsonify({'error': 'Request origin is not allowed.'}), 403
        if request.headers.get('Sec-Fetch-Site', '').lower() == 'cross-site':
            return jsonify({'error': 'Cross-site state changes are not allowed.'}), 403

    if ENVIRONMENT == 'production' and SERVICE_ROLE == 'frontend' and request.path.startswith('/api/'):
        return _proxy_api_request()
    return None


def _proxy_api_request():
    backend_url = os.environ.get('BACKEND_URL', '').strip().rstrip('/')
    if not backend_url:
        current_app.logger.error('BACKEND_URL is missing on the frontend service')
        return jsonify({'error': 'The learning service is not configured yet.'}), 503
    if request.method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
        return jsonify({'error': 'Unsupported API method.'}), 405

    query = ('?' + request.query_string.decode('latin-1')) if request.query_string else ''
    destination = backend_url + request.path + query
    headers = {}
    for name in ('Content-Type', 'Accept', 'Cookie', 'Origin', 'Authorization', 'X-CSRF-Token'):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    body = request.get_data(cache=False) if request.method not in ('GET', 'HEAD') else None
    upstream_request = UpstreamRequest(destination, data=body, headers=headers, method=request.method)
    try:
        timeout = float(os.environ.get('API_PROXY_TIMEOUT_SECONDS', '90'))
        try:
            upstream = urlopen(upstream_request, timeout=timeout)
        except HTTPError as exc:
            upstream = exc
        with upstream:
            payload = upstream.read(256 * 1024)
            response_headers = []
            for key in ('Content-Type', 'Cache-Control', 'Retry-After'):
                value = upstream.headers.get(key)
                if value:
                    response_headers.append((key, value))
            for value in upstream.headers.get_all('Set-Cookie', []):
                response_headers.append(('Set-Cookie', value))
            return Response(payload, status=upstream.status, headers=response_headers)
    except URLError as exc:
        current_app.logger.warning('Backend API proxy failed: %s', type(exc.reason).__name__)
        return jsonify({'error': 'The learning service is temporarily unavailable. Please retry.'}), 503
    except (TimeoutError, OSError) as exc:
        current_app.logger.warning('Backend API proxy timed out or could not connect: %s', type(exc).__name__)
        return jsonify({'error': 'The learning service is waking up or temporarily unavailable. Please retry.'}), 503


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/ready')
def readiness():
    conn = None
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.fetchone()
        return jsonify({'status': 'ready', 'database': 'connected'})
    except Exception:
        current_app.logger.exception('Database readiness check failed')
        return jsonify({'status': 'not_ready', 'database': 'unavailable'}), 503
    finally:
        if conn is not None:
            conn.close()

# ─────────────────────────── DB INIT ──────────────────────────────

def init_db():
    initialize_database()

def get_db():
    conn = connect_db()
    if has_app_context():
        g.setdefault('_bounty_db_connections', []).append(conn)
    return conn


@app.teardown_appcontext
def close_request_databases(_error=None):
    for conn in g.pop('_bounty_db_connections', []):
        try:
            conn.close()
        except Exception:
            current_app.logger.exception('Failed to close a database connection')

init_db()

# ─────────────────────────── ENTRY & AUTH ROUTES ──────────────────────

@app.route('/')
@app.route('/start')
def start():
    username = session.get('username', '')
    return render_template('start.html', username=username)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    identifier = request.form.get('email', '').strip()
    lookup_identifier = identifier.lower() if '@' in identifier else identifier
    password = request.form.get('password', '')

    if not identifier or not password:
        return render_template('login.html', error='Email/username and password required')

    conn = get_db()
    c = conn.cursor()

    # Accept email OR username
    c.execute('SELECT id, username, password FROM users WHERE email = ? OR username = ?', (lookup_identifier, identifier))
    user = c.fetchone()
    conn.close()

    if user is None:
        return render_template('login.html', error='Account not found')

    if not check_password_hash(user['password'], password):
        return render_template('login.html', error='Incorrect password')

    session.clear()
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']

    return redirect(url_for('home'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not username or not email or not password:
        return render_template('signup.html', error='All fields required')

    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', username):
        return render_template('signup.html', error='Username must be 3–32 characters using letters, numbers, dots, dashes, or underscores')

    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        return render_template('signup.html', error='Enter a valid email address')

    if password != confirm_password:
        return render_template('signup.html', error='Passwords do not match')

    if len(password) < 10:
        return render_template('signup.html', error='Password must be at least 10 characters')

    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT id FROM users WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        return render_template('signup.html', error='Username already taken')

    c.execute('SELECT id FROM users WHERE email = ?', (email,))
    if c.fetchone():
        conn.close()
        return render_template('signup.html', error='Email already registered')

    hashed_password = generate_password_hash(password)

    try:
        if is_postgres_enabled():
            c.execute('INSERT INTO users (username, email, password, total_bounty) VALUES (?, ?, ?, ?) RETURNING id',
                      (username, email, hashed_password, 0))
            user_id = c.fetchone()['id']
        else:
            c.execute('INSERT INTO users (username, email, password, total_bounty) VALUES (?, ?, ?, ?)',
                      (username, email, hashed_password, 0))
            user_id = c.lastrowid

        # Create default profile
        c.execute('INSERT INTO user_profiles (user_id, display_name, pirate_group, avatar) VALUES (?, ?, ?, ?)',
                  (user_id, username, 'Straw Hat Pirates', 'luffy'))
        conn.commit()
        conn.close()

        session.clear()
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username

        return redirect(url_for('home'))

    except Exception:
        conn.rollback()
        conn.close()
        current_app.logger.exception('Signup failed')
        return render_template('signup.html', error='Could not create the account. Please try again.')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─────────────────────────── MAIN PAGES ──────────────────────────────

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    bounty_updated = session.pop('bounty_updated', False) or request.args.get('bounty_updated') == '1'
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT total_bounty FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()

    # Profile
    c.execute('SELECT display_name, pirate_group, avatar FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = c.fetchone()

    conn.close()
    if profile:
        profile = dict(profile)
        profile['avatar'] = normalize_avatar(profile.get('avatar'))

    return render_template('home.html',
        username=session['username'],
        total_bounty=user['total_bounty'] if user else 0,
        profile=profile,
        bounty_updated=bounty_updated
    )


@app.route('/course_select')
def course_select():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('course_select.html', username=session['username'])


@app.route('/game/<course_id>')
def game(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT name, language FROM courses WHERE id = ?', (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        return redirect(url_for('course_select'))

    # Check for existing progress
    c.execute('''SELECT * FROM progress WHERE user_id = ? AND course_id = ? AND completed = 0
                 ORDER BY last_updated DESC LIMIT 1''', (user_id, course_id))
    existing = c.fetchone()

    conn.close()

    has_save = existing is not None

    return render_template('game.html',
        course_id=course_id,
        course_name=course['name'],
        course_language=course['language'],
        username=session['username'],
        has_save=has_save
    )


@app.route('/completion/<course_id>')
def completion(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT name FROM courses WHERE id = ?', (course_id,))
    course = c.fetchone()

    c.execute('SELECT display_name, pirate_group, avatar FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = c.fetchone()

    # Get bounty for this course
    c.execute('''SELECT bounty FROM bounty_records WHERE user_id = ? AND course_id = ?
                 ORDER BY completed_at DESC LIMIT 1''', (user_id, course_id))
    bounty_row = c.fetchone()
    bounty = bounty_row['bounty'] if bounty_row else 0

    conn.close()

    display_name = profile['display_name'] if profile else session['username']
    pirate_group = profile['pirate_group'] if profile else 'Straw Hat Pirates'
    avatar = normalize_avatar(profile['avatar']) if profile else 'luffy'

    return render_template('completion.html',
        course_name=course['name'] if course else 'Unknown',
        display_name=display_name,
        pirate_group=pirate_group,
        avatar=avatar,
        bounty=bounty
    )


# ─────────────────────────── API ROUTES ──────────────────────────────

@app.route('/api/get_questions', methods=['POST'])
def api_get_questions():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    level = data.get('level')  # 'easy', 'medium', 'hard'

    if not course_id or not level:
        return jsonify({'error': 'Missing params'}), 400

    conn = get_db()
    c = conn.cursor()

    # Get question groups for this course + level (5 groups, 3 alternatives each)
    c.execute('''SELECT * FROM questions WHERE course_id = ? AND level = ?
                 ORDER BY id''', (course_id, level))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return jsonify({'error': f'No questions found for course {course_id} level {level}'}), 404

    # Group by question group (each row has 3 alternatives)
    selected = []
    for row in rows:
        # Randomly pick alternative 1, 2, or 3
        alt = random.randint(1, 3)
        question_text = row[f'question_text_{alt}']
        expected_output = row[f'expected_output_{alt}']

        selected.append({
            'id': row['id'],
            'question_text': question_text,
            'expected_output': expected_output,
            'opponent_name': row['opponent_name'],
            'language': row['language'],
            'alt': alt
        })

    return jsonify({'questions': selected})


@app.route('/api/start_session', methods=['POST'])
def api_start_session():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    force_new = data.get('force_new', False)

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    if not force_new:
        # Check for existing progress
        c.execute('''SELECT * FROM progress WHERE user_id = ? AND course_id = ? AND completed = 0
                     ORDER BY last_updated DESC LIMIT 1''', (user_id, course_id))
        existing = c.fetchone()
        if existing:
            session_questions = json.loads(existing['session_questions']) if existing['session_questions'] else None
            conn.close()
            return jsonify({
                'resumed': True,
                'current_level': existing['current_level'],
                'current_question_number': existing['current_question_number'],
                'bounty_earned': existing['bounty_earned'],
                'session_questions': session_questions
            })

    # Delete old incomplete progress for this course
    c.execute('DELETE FROM progress WHERE user_id = ? AND course_id = ? AND completed = 0',
              (user_id, course_id))

    # Generate all 15 questions randomly
    all_questions = {}
    for level in ['easy', 'medium', 'hard']:
        c.execute('''SELECT * FROM questions WHERE course_id = ? AND level = ? ORDER BY id''',
                  (course_id, level))
        rows = c.fetchall()
        level_questions = []
        for row in rows:
            alt = random.randint(1, 3)
            level_questions.append({
                'id': row['id'],
                'question_text': row[f'question_text_{alt}'],
                'expected_output': row[f'expected_output_{alt}'],
                'opponent_name': row['opponent_name'],
                'language': row['language'],
                'alt': alt
            })
        all_questions[level] = level_questions

    session_json = json.dumps(all_questions)

    c.execute('''INSERT INTO progress (user_id, course_id, current_level, current_question_number, completed, session_questions, bounty_earned)
                 VALUES (?, ?, 'easy', 1, 0, ?, 0)''',
              (user_id, course_id, session_json))
    conn.commit()
    conn.close()

    return jsonify({
        'resumed': False,
        'current_level': 'easy',
        'current_question_number': 1,
        'bounty_earned': 0,
        'session_questions': all_questions
    })


@app.route('/api/submit_answer', methods=['POST'])
def api_submit_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    level = data.get('level')
    question_number = data.get('question_number')
    user_code = data.get('code', '')
    expected_output = data.get('expected_output', '').strip()
    language = data.get('language', 'Python')
    # Comparison mode: 'normalized' (default), 'strict', 'numeric', 'custom'
    comparison_mode = data.get('comparison_mode', 'normalized')

    # Run user code and capture output
    result = run_code(user_code, language)

    # ── Distinguish error types ──────────────────────────────────────────
    if result['error']:
        error_msg = result['error']
        error_type = classify_error(result)
        return jsonify({
            'correct': False,
            'error': error_msg,
            'error_type': error_type,
            'output': result.get('output', ''),
            'expected': expected_output
        })

    # ── Compare output ───────────────────────────────────────────────────
    actual_output = result['output']

    if language.lower() in ('html and css', 'html/css'):
        # Use the structural HTML parser instead of whole-string keyword search.
        # actual_output for HTML is the submitted source code (set by run_code).
        html_result = evaluate_html(actual_output, expected_output)
        correct = html_result.is_correct
        cmp_detail = html_result.detail if not correct else ''
    else:
        cmp_result = compare_outputs(
            actual_output,
            expected_output,
            mode=comparison_mode,
        )
        correct = cmp_result.is_correct
        cmp_detail = cmp_result.detail

    if correct:
        # Update progress
        user_id = session['user_id']
        conn = get_db()
        c = conn.cursor()

        # Determine next state
        next_q = question_number + 1
        next_level = level
        completed = 0

        if question_number >= 5:
            if level == 'easy':
                next_level = 'medium'
                next_q = 1
            elif level == 'medium':
                next_level = 'hard'
                next_q = 1
            elif level == 'hard':
                completed = 1
                next_level = 'hard'
                next_q = 5

        # Bounty calculation
        bounty_per_correct = {'easy': 5_000_000, 'medium': 10_000_000, 'hard': 15_000_000}
        bounty_gain = bounty_per_correct.get(level, 5_000_000)

        c.execute('''UPDATE progress SET current_level = ?, current_question_number = ?,
                     completed = ?, bounty_earned = bounty_earned + ?, last_updated = CURRENT_TIMESTAMP
                     WHERE user_id = ? AND course_id = ? AND completed = 0''',
                  (next_level, next_q, completed, bounty_gain, user_id, course_id))
        rows_affected = c.rowcount

        # Update total bounty
        c.execute('UPDATE users SET total_bounty = total_bounty + ? WHERE id = ?',
                  (bounty_gain, user_id))
        session['bounty_updated'] = True

        if completed and rows_affected > 0:
            # Save bounty record
            c.execute('SELECT name FROM courses WHERE id = ?', (course_id,))
            course = c.fetchone()
            c.execute('''SELECT bounty_earned FROM progress WHERE user_id = ? AND course_id = ? AND completed = 1
                         ORDER BY last_updated DESC LIMIT 1''', (user_id, course_id))
            prog = c.fetchone()
            total_bounty = prog['bounty_earned'] if prog else bounty_gain

            c.execute('''INSERT INTO bounty_records (user_id, course_id, course_name, bounty)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, course_id, course['name'] if course else course_id, total_bounty))

        conn.commit()
        conn.close()

    return jsonify({
        'correct': correct,
        'output': actual_output.strip(),
        'expected': expected_output,
        'error': None,
        'error_type': None,
        'comparison_detail': cmp_detail if not correct else ''
    })




@app.route('/api/lose_heart', methods=['POST'])
def api_lose_heart():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    level = data.get('level')

    bounty_penalty = {'easy': 2_000_000, 'medium': 5_000_000, 'hard': 8_000_000}
    penalty = bounty_penalty.get(level, 2_000_000)

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    # Don't go below 0
    c.execute('''UPDATE users SET total_bounty = CASE WHEN total_bounty > ? THEN total_bounty - ? ELSE 0 END WHERE id = ?''',
              (penalty, penalty, user_id))
    c.execute('''UPDATE progress SET bounty_earned = CASE WHEN bounty_earned > ? THEN bounty_earned - ? ELSE 0 END
                 WHERE user_id = ? AND course_id = ? AND completed = 0''',
              (penalty, penalty, user_id, course_id))
    conn.commit()

    c.execute('SELECT total_bounty FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()

    return jsonify({'new_bounty': user['total_bounty']})


@app.route('/api/save_video_time', methods=['POST'])
def api_save_video_time():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    video_time = data.get('video_time', 0)
    stage = data.get('stage', 'easy')

    user_id = session['user_id']
    session[f'video_time_{course_id}_{stage}'] = video_time

    return jsonify({'saved': True})


@app.route('/api/get_video_time', methods=['POST'])
def api_get_video_time():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    stage = data.get('stage', 'easy')

    video_time = session.get(f'video_time_{course_id}_{stage}', 0)
    return jsonify({'video_time': video_time})


@app.route('/api/complete_course', methods=['POST'])
def api_complete_course():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')
    user_id = session['user_id']

    conn = get_db()
    c = conn.cursor()

    c.execute('''UPDATE progress SET completed = 1, last_updated = CURRENT_TIMESTAMP
                 WHERE user_id = ? AND course_id = ? AND completed = 0''',
              (user_id, course_id))
    was_uncompleted = (c.rowcount > 0)

    # Only insert/record if this completion was not already processed
    if was_uncompleted:
        c.execute('SELECT name FROM courses WHERE id = ?', (course_id,))
        course = c.fetchone()

        c.execute('''SELECT bounty_earned FROM progress WHERE user_id = ? AND course_id = ?
                     ORDER BY last_updated DESC LIMIT 1''', (user_id, course_id))
        prog = c.fetchone()
        bounty = prog['bounty_earned'] if prog else 0

        # Insert/update bounty record
        c.execute('''INSERT INTO bounty_records (user_id, course_id, course_name, bounty)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, course_id, course['name'] if course else course_id, bounty))

    conn.commit()
    conn.close()

    session['bounty_updated'] = True

    return jsonify({'success': True})


@app.route('/api/quit_course', methods=['POST'])
def api_quit_course():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    course_id = data.get('course_id')

    # Keep progress but flag as quit by preserving the record (user can resume)
    return jsonify({'success': True})


@app.route('/api/course_history')
def api_course_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    # Ongoing
    c.execute('''SELECT p.course_id, c.name, p.current_level, p.current_question_number, p.bounty_earned
                 FROM progress p JOIN courses c ON p.course_id = c.id
                 WHERE p.user_id = ? AND p.completed = 0
                 ORDER BY p.last_updated DESC''', (user_id,))
    ongoing = [dict(r) for r in c.fetchall()]

    # Completed
    c.execute('''SELECT p.course_id, c.name, COUNT(*) as times,
                        MAX(p.bounty_earned) as best_bounty
                 FROM progress p JOIN courses c ON p.course_id = c.id
                 WHERE p.user_id = ? AND p.completed = 1
                 GROUP BY p.course_id
                 ORDER BY best_bounty DESC''', (user_id,))
    completed = [dict(r) for r in c.fetchall()]

    conn.close()
    return jsonify({'ongoing': ongoing, 'completed': completed})


def deduplicate_bounty_records(records):
    """
    Ensure each distinct course completion has at most one bounty record.
    If multiple records exist within 60 seconds of each other for the same course run,
    keep only the single correct earned record.
    """
    if not records or len(records) <= 1:
        return records

    sorted_recs = sorted(records, key=lambda r: (str(r.get('completed_at') or ''), r.get('id', 0)))
    deduped = []
    for r in sorted_recs:
        if not deduped:
            deduped.append(r)
            continue
        last = deduped[-1]
        is_same_course = (
            r.get('course_id') == last.get('course_id') or
            r.get('course_name') == last.get('course_name')
        )
        diff = 999999
        try:
            t_curr = datetime.strptime(str(r.get('completed_at') or '')[:19], '%Y-%m-%d %H:%M:%S')
            t_last = datetime.strptime(str(last.get('completed_at') or '')[:19], '%Y-%m-%d %H:%M:%S')
            diff = abs((t_curr - t_last).total_seconds())
        except Exception:
            pass

        if is_same_course and diff <= 60:
            # Duplicate from the same completion session
            if (last.get('bounty', 0) - r.get('bounty', 0)) == 15_000_000:
                deduped[-1] = r
        else:
            deduped.append(r)

    return deduped


@app.route('/api/bounty_records')
def api_bounty_records():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    c.execute('''SELECT course_name, bounty, completed_at FROM bounty_records
                 WHERE user_id = ? ORDER BY bounty DESC''', (user_id,))
    records = deduplicate_bounty_records([dict(r) for r in c.fetchall()])

    c.execute('SELECT total_bounty FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()

    conn.close()
    return jsonify({'records': records, 'total_bounty': user['total_bounty'] if user else 0})


def select_top_bounty_posters(records):
    """
    Select up to 5 posters for a course based on project rules:
    - Case A: < 5 records: all qualifying records.
    - Case B: == 5 records: all 5 records.
    - Case C: > 5 records:
        1. 5 highest distinct bounty amounts (highest to lowest).
        2. If fewer than 5 distinct amounts exist, fill remaining slots
           using additional real earned records with repeated amounts,
           ordered by bounty DESC, then completed_at DESC (tie-breaker).
    """
    if not records:
        return []

    sorted_records = sorted(
        records,
        key=lambda r: (r.get('bounty', 0), str(r.get('completed_at') or ''), r.get('id', 0)),
        reverse=True
    )

    if len(sorted_records) <= 5:
        res = []
        for idx, r in enumerate(sorted_records, 1):
            item = dict(r)
            item['rank'] = idx
            res.append(item)
        return res

    first_choice = []
    seen_amounts = set()
    first_choice_ids = set()

    for r in sorted_records:
        amt = r.get('bounty', 0)
        if amt not in seen_amounts:
            seen_amounts.add(amt)
            first_choice.append(r)
            first_choice_ids.add(r.get('id'))
            if len(first_choice) == 5:
                break

    if len(first_choice) >= 5:
        selected = first_choice
    else:
        selected = list(first_choice)
        for r in sorted_records:
            if r.get('id') not in first_choice_ids:
                selected.append(r)
                if len(selected) == 5:
                    break

    selected.sort(
        key=lambda r: (r.get('bounty', 0), str(r.get('completed_at') or ''), r.get('id', 0)),
        reverse=True
    )

    res = []
    for idx, r in enumerate(selected, 1):
        item = dict(r)
        item['rank'] = idx
        res.append(item)
    return res


@app.route('/api/bounty_collection')
def api_bounty_collection():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    # User info
    c.execute('SELECT username, total_bounty FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    # Profile info
    c.execute('SELECT display_name, pirate_group, avatar FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = c.fetchone()

    avatar_name = normalize_avatar(profile['avatar'] if profile else 'luffy')
    avatar_ext = '.jpg' if avatar_name in ['brook', 'franky', 'robin'] else '.png'
    avatar_url = f"/static/avatars/{avatar_name}{avatar_ext}"

    user_data = {
        'username': user['username'],
        'display_name': (profile['display_name'] if profile and profile['display_name'] else user['username']),
        'pirate_group': (profile['pirate_group'] if profile and profile['pirate_group'] else 'Straw Hat Pirates'),
        'avatar': avatar_name,
        'avatar_url': avatar_url,
        'total_bounty': user['total_bounty'] or 0
    }

    courses_def = [
        {'key': 'python', 'id': '101', 'name': 'Python', 'full_name': 'Python Basics'},
        {'key': 'java',   'id': '102', 'name': 'Java',   'full_name': 'Java Basics'},
        {'key': 'html',   'id': '103', 'name': 'HTML',   'full_name': 'HTML & CSS'},
        {'key': 'c',      'id': '104', 'name': 'C',      'full_name': 'C Language'},
    ]

    collection = {}
    for cinfo in courses_def:
        cid = cinfo['id']
        cname = cinfo['name']
        cfullname = cinfo['full_name']

        c.execute('''SELECT id, course_id, course_name, bounty, completed_at
                     FROM bounty_records
                     WHERE user_id = ? AND (course_id = ? OR course_name = ?)
                     ORDER BY bounty DESC, completed_at DESC, id DESC''',
                  (user_id, cid, cfullname))
        raw_rows = [dict(r) for r in c.fetchall()]
        raw_rows = deduplicate_bounty_records(raw_rows)
        total_plays = len(raw_rows)

        posters = select_top_bounty_posters(raw_rows)
        for p in posters:
            bval = p.get('bounty', 0) or 0
            p['formatted_bounty'] = f"{bval:,}"

        collection[cinfo['key']] = {
            'id': cid,
            'name': cname,
            'full_name': cfullname,
            'total_plays': total_plays,
            'posters': posters
        }

    conn.close()

    requested_course = request.args.get('course', '').lower().strip()
    if requested_course and requested_course in collection:
        return jsonify({
            'user': user_data,
            'course': collection[requested_course],
            'courses': collection
        })

    return jsonify({
        'user': user_data,
        'courses': collection
    })


@app.route('/api/update_profile', methods=['POST'])
def api_update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A valid profile object is required.'}), 400
    user_id = session['user_id']
    display_name = data.get('display_name', session['username'])
    pirate_group = data.get('pirate_group', 'Straw Hat Pirates')
    raw_avatar = data.get('avatar', 'luffy')
    if not isinstance(display_name, str) or not isinstance(pirate_group, str) or not isinstance(raw_avatar, str):
        return jsonify({'error': 'Profile fields must be text.'}), 400
    display_name = display_name.strip() or session['username']
    pirate_group = pirate_group.strip() or 'Straw Hat Pirates'
    if len(display_name) > 40 or len(pirate_group) > 40:
        return jsonify({'error': 'Profile names must be 40 characters or fewer.'}), 400
    if raw_avatar.strip().casefold() not in AVATAR_NAMES:
        return jsonify({'error': 'Choose an avatar from the available list.'}), 400
    avatar = normalize_avatar(raw_avatar)

    conn = get_db()
    c = conn.cursor()

    c.execute('''INSERT INTO user_profiles (user_id, display_name, pirate_group, avatar)
                 VALUES (?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET
                 display_name=excluded.display_name,
                 pirate_group=excluded.pirate_group,
                 avatar=excluded.avatar''',
              (user_id, display_name, pirate_group, avatar))
    conn.commit()
    conn.close()

    session['bounty_updated'] = True

    return jsonify({'success': True})


@app.route('/api/get_profile')
def api_get_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT display_name, pirate_group, avatar FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = c.fetchone()
    conn.close()

    if profile:
        return jsonify({
            'display_name': profile['display_name'],
            'pirate_group': profile['pirate_group'],
            'avatar': normalize_avatar(profile['avatar'])
        })
    return jsonify({
        'display_name': session['username'],
        'pirate_group': 'Straw Hat Pirates',
        'avatar': 'luffy'
    })


# ─────────────────────────── CODE EXECUTION ──────────────────────────────

def _find_c_compiler():
    """Locate gcc or clang: PATH first, then common Windows install paths."""
    for name in ('gcc', 'clang'):
        found = shutil.which(name)
        if found:
            return found

    for env_var in ('MINGW_HOME', 'GCC_HOME', 'MSYS2_HOME'):
        val = os.environ.get(env_var)
        if val:
            for sub in ('bin', ''):
                for name in ('gcc.exe', 'clang.exe'):
                    cand = os.path.join(val, sub, name) if sub else os.path.join(val, name)
                    if os.path.isfile(cand):
                        return cand

    search_dirs = [
        r'C:\mingw64\bin',
        r'C:\msys64\ucrt64\bin',
        r'C:\msys64\mingw64\bin',
        r'C:\msys64\usr\bin',
        r'C:\MinGW\bin',
        r'C:\TDM-GCC-64\bin',
        r'C:\w64devkit\bin',
        r'C:\Program Files\LLVM\bin',
    ]
    for d in search_dirs:
        for name in ('gcc.exe', 'clang.exe'):
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                return cand

    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    if os.path.isdir(pf):
        try:
            for entry in os.listdir(pf):
                if 'mingw' in entry.lower():
                    for sub in (['bin'], ['mingw64', 'bin'], ['x86_64-w64-mingw32', 'bin']):
                        cand = os.path.join(pf, entry, *sub, 'gcc.exe')
                        if os.path.isfile(cand):
                            return cand
        except OSError:
            pass

    return None


def _find_java_tool(tool_name):
    """Locate javac or java: PATH first, JAVA_HOME, then common Windows locations."""
    found = shutil.which(tool_name)
    if found:
        return found

    exe_name = tool_name + ('.exe' if os.name == 'nt' else '')

    for env_var in ('JAVA_HOME', 'JDK_HOME'):
        val = os.environ.get(env_var)
        if val:
            cand = os.path.join(val, 'bin', exe_name)
            if os.path.isfile(cand):
                return cand

    direct_dirs = [
        r'C:\Program Files\Android\Android Studio\jbr\bin',
    ]
    for d in direct_dirs:
        cand = os.path.join(d, exe_name)
        if os.path.isfile(cand):
            return cand

    base_dirs = [
        r'C:\Program Files\Java',
        r'C:\Program Files\Eclipse Adoptium',
        r'C:\Program Files\Microsoft',
        r'C:\Program Files\OpenJDK',
        r'C:\Program Files\Amazon Corretto',
        r'C:\Program Files\Zulu',
    ]
    for base in base_dirs:
        if os.path.isdir(base):
            cand = os.path.join(base, 'bin', exe_name)
            if os.path.isfile(cand):
                return cand
            try:
                for entry in os.listdir(base):
                    cand = os.path.join(base, entry, 'bin', exe_name)
                    if os.path.isfile(cand):
                        return cand
            except OSError:
                pass

    return None


def run_code(code, language):
    """Execute user code safely and return output"""
    try:
        if language.lower() in ('python', 'python basics'):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                fname = f.name
            try:
                result = subprocess.run(
                    [sys.executable, fname],
                    capture_output=True, text=True, timeout=90
                )
                output = result.stdout
                error = result.stderr if result.returncode != 0 else None
                return {'output': output, 'error': error}
            finally:
                os.unlink(fname)

        elif language.lower() in ('java', 'java basics'):
            javac_exe = _find_java_tool('javac')
            java_exe  = _find_java_tool('java')

            if not javac_exe or not java_exe:
                return {
                    'output': '',
                    'error': (
                        'Java compiler not found. '
                        'Please install a JDK (e.g. OpenJDK or Eclipse Temurin) and '
                        'ensure javac and java are on the system PATH.'
                    ),
                    'error_type': 'compilation_error',
                }

            # Handle optional package declaration and class name
            pkg_match = re.search(r'^\s*package\s+([a-zA-Z0-9_.]+)\s*;', code, re.MULTILINE)
            class_match = re.search(r'public\s+class\s+(\w+)', code) or re.search(r'class\s+(\w+)', code)
            class_name = class_match.group(1) if class_match else 'Main'

            tmpdir = tempfile.mkdtemp()
            try:
                if pkg_match:
                    pkg_name = pkg_match.group(1)
                    pkg_dir = os.path.join(tmpdir, *pkg_name.split('.'))
                    os.makedirs(pkg_dir, exist_ok=True)
                    java_file = os.path.join(pkg_dir, f'{class_name}.java')
                    full_class_name = f'{pkg_name}.{class_name}'
                else:
                    java_file = os.path.join(tmpdir, f'{class_name}.java')
                    full_class_name = class_name

                with open(java_file, 'w', encoding='utf-8') as f:
                    f.write(code)

                if not os.path.isfile(java_file):
                    return {'output': '', 'error': 'Failed to create Java source file',
                            'error_type': 'compilation_error'}

                compile_result = subprocess.run(
                    [javac_exe, java_file],
                    capture_output=True, text=True, timeout=60, cwd=tmpdir
                )
                if compile_result.returncode != 0:
                    return {'output': '', 'error': compile_result.stderr or compile_result.stdout or 'Compilation failed',
                            'error_type': 'compilation_error'}

                # Confirm class was compiled
                expected_class_file = os.path.splitext(java_file)[0] + '.class'
                if not os.path.isfile(expected_class_file):
                    return {'output': '', 'error': 'Compilation failed: class file was not generated',
                            'error_type': 'compilation_error'}

                run_result = subprocess.run(
                    [java_exe, '-cp', tmpdir, full_class_name],
                    capture_output=True, text=True, timeout=30, cwd=tmpdir
                )
                if run_result.returncode != 0:
                    return {'output': run_result.stdout, 'error': run_result.stderr or f'Runtime error (exit code {run_result.returncode})',
                            'error_type': 'runtime_error'}
                return {'output': run_result.stdout, 'error': None}
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        elif language.lower() in ('html and css', 'html/css'):
            # For HTML, return code as output for structural evaluation
            return {'output': code, 'error': None}

        elif language.lower() in ('c', 'c language'):
            gcc_exe = _find_c_compiler()
            if not gcc_exe:
                return {
                    'output': '',
                    'error': (
                        'C compiler not found. '
                        'Please install GCC (e.g. MinGW-w64, WinLibs, or MSYS2) and '
                        'ensure gcc is added to the system PATH.'
                    ),
                    'error_type': 'compilation_error',
                }

            tmpdir = tempfile.mkdtemp()
            try:
                c_file = os.path.join(tmpdir, 'main.c')
                exe_file = os.path.join(tmpdir, 'main.exe' if os.name == 'nt' else 'main')
                with open(c_file, 'w', encoding='utf-8') as f:
                    f.write(code)

                if not os.path.isfile(c_file):
                    return {'output': '', 'error': 'Failed to create C source file',
                            'error_type': 'compilation_error'}

                compile_result = subprocess.run(
                    [gcc_exe, c_file, '-o', exe_file],
                    capture_output=True, text=True, timeout=30, cwd=tmpdir
                )
                if compile_result.returncode != 0:
                    return {'output': '', 'error': compile_result.stderr or compile_result.stdout or 'Compilation failed',
                            'error_type': 'compilation_error'}

                if not os.path.isfile(exe_file):
                    return {'output': '', 'error': 'Compilation failed: executable was not generated',
                            'error_type': 'compilation_error'}

                run_result = subprocess.run(
                    [exe_file],
                    capture_output=True, text=True, timeout=20, cwd=tmpdir
                )
                if run_result.returncode != 0:
                    return {'output': run_result.stdout, 'error': run_result.stderr or f'Runtime error (exit code {run_result.returncode})',
                            'error_type': 'runtime_error'}
                return {'output': run_result.stdout, 'error': None}
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            return {'output': '', 'error': f'Unsupported language: {language}',
                    'error_type': 'unsupported_language'}

    except subprocess.TimeoutExpired:
        return {'output': '', 'error': 'Code execution timed out',
                'error_type': 'timeout'}
    except FileNotFoundError as e:
        return {'output': '', 'error': f'Required executable or file not found: {e.filename or str(e)}',
                'error_type': 'compilation_error'}
    except Exception as e:
        return {'output': '', 'error': str(e), 'error_type': 'runtime_error'}


def compare_output(actual, expected, language):
    """
    Legacy comparison helper — kept for safety but no longer called by
    api_submit_answer.

    HTML/CSS submissions now go through html_evaluator.evaluate_html().
    All other language submissions go through evaluator.compare_outputs().
    This function is retained so any external callers are not broken.
    """
    if language.lower() in ('html and css', 'html/css'):
        # Legacy keyword-presence check (superseded by html_evaluator)
        keywords = [k.strip() for k in expected.split(' and ')]
        actual_lower = actual.lower()
        return all(kw.lower() in actual_lower for kw in keywords)

    # Normalize whitespace
    actual_norm = '\n'.join(line.strip() for line in actual.strip().splitlines())
    expected_norm = '\n'.join(line.strip() for line in expected.strip().splitlines())
    return actual_norm == expected_norm


# ─────────────────────────── RUN ──────────────────────────────

# BEGIN BOUNTY_ENGINE_V2
import bounty_engine
bounty_engine.install(app, get_db, run_code, compare_outputs, classify_error, evaluate_html)
# END BOUNTY_ENGINE_V2

@app.errorhandler(500)
def internal_error(_error):
    current_app.logger.exception('Unhandled application error')
    if request.path.startswith('/api/'):
        return jsonify({'error': 'An unexpected server error occurred.'}), 500
    return render_template('start.html'), 500


if __name__ == '__main__':
    host = '0.0.0.0' if ENVIRONMENT == 'production' else os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    app.run(host=host, port=port, debug=False, use_reloader=False)
