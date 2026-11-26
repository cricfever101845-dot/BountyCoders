from dotenv import load_dotenv
from flask import Flask, Response, current_app, g, has_app_context, render_template, request, redirect, session, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import json
import random
import re
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

if os.environ.get('BCTEST_DISABLE_DOTENV') != '1':
    load_dotenv(override=False)

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

def run_code(code, language):
    """Use the isolated execution provider; never launch student programs locally."""
    from code_execution import execute_code, ProviderFailure
    try:
        result = execute_code(code, language)
        return {
            'output': result.output,
            'error': result.error,
            'error_type': result.error_type,
            'provider_error': False,
            'ran': result.ran,
        }
    except ProviderFailure as exc:
        return {'output': '', 'error': str(exc), 'error_type': 'provider_error', 'provider_error': True}
    except ValueError as exc:
        return {'output': '', 'error': str(exc), 'error_type': 'invalid_code', 'provider_error': False}


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
