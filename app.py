from flask import Flask,render_template,request,redirect,url_for
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




    