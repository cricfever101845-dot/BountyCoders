from flask import Flask,render_template,request,redirect, session,url_for
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import subprocess
from datetime import datetime
import random

app=Flask(__name__)
app.secret_key = 'onepiece-secret-key-2026'

def init_db():
    conn = sqlite3.connect('bountycoders.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        total_bounty INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS courses
    (id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS questions
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    question_number INTEGER NOT NULL,
    question_text_1 TEXT NOT NULL,
    expected_output_1 TEXT NOT NULL,
    question_text_2 TEXT NOT NULL,
    expected_output_2 TEXT NOT NULL,
    question_text_3 TEXT NOT NULL,
    expected_output_3 TEXT NOT NULL,
    opponent_name TEXT NOT NULL,
    language TEXT NOT NULL,
    FOREIGN KEY (course_id) REFERENCES courses(id))
    ''')

    c.execute('''CREATE TABLE IF NOT EXISTS progress (
       user_id INTEGER NOT NULL,
       course_id INTEGER NOT NULL,
       current_question_id INTEGER,
       last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (user_id) REFERENCES users(id),
       FOREIGN KEY (course_id) REFERENCES courses(id),
       FOREIGN KEY (current_question_id) REFERENCES questions(id)
    )''')

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('bountycoders.db')
    conn.row_factory = sqlite3.Row
    return conn

init_db()

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if not username or not email or not password:
        return render_template('signup.html', error='All fields required')
    
    if password != confirm_password:
        return render_template('signup.html', error='Passwords do not match')
    
    if len(password) < 6:
        return render_template('signup.html', error='Password must be 6+ characters')
    
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
        c.execute('INSERT INTO users (username, email, password, total_bounty) VALUES (?, ?, ?, ?)',
                 (username, email, hashed_password, 0))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        session['user_id'] = user_id
        session['username'] = username
        
        return redirect(url_for('dashboard1'))
    
    except Exception as e:
        conn.close()
        return render_template('signup.html', error=f'Error: {str(e)}')

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    email = request.form.get('email')
    password = request.form.get('password')
    
    if not email or not password:
        return render_template('login.html', error='Email and password required')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT id, username, password FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    
    if user is None:
        return render_template('login.html', error='Email does not exist')
    
    if not check_password_hash(user['password'], password):
        return render_template('login.html', error='Incorrect password')
    
    session['user_id'] = user['id']
    session['username'] = user['username']
    
    return redirect(url_for('dashboard1'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard1')
def dashboard1():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('dashboard1.html', username=session['username'])

@app.route('/dashboard2')
def dashboard2():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT total_bounty, created_at FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    
    
    c.execute('''SELECT course_id FROM progress 
                 WHERE user_id = ? AND completed = 0 LIMIT 1''', (user_id,))
    ongoing = c.fetchone()
    
    
    c.execute('''SELECT COUNT(*) as count FROM progress 
                 WHERE user_id = ? AND completed = 1''', (user_id,))
    completed_count = c.fetchone()['count']
    
    
    c.execute('''SELECT COUNT(*) as count FROM progress 
                 WHERE user_id = ?''', (user_id,))
    total_attempts = c.fetchone()['count']
    
    conn.close()
    
    joined_date = datetime.strptime(user['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
    
    return render_template('dashboard2.html',
                          username=session['username'],
                          bounty=user['total_bounty'],
                          current_course='Python' if ongoing else 'None',
                          current_progress=0,
                          completed_count=completed_count,
                          total_attempts=total_attempts,
                          joined_date=joined_date)

    