"""
migrate_db.py — Run this once to migrate the database schema and seed questions.
"""
import sqlite3
from datetime import datetime

def migrate_and_seed():
    conn = sqlite3.connect('bountycoders.db')
    c = conn.cursor()

    # ── 1. Drop and recreate progress table with new schema ──────────────────
    c.execute('DROP TABLE IF EXISTS progress')
    c.execute('''CREATE TABLE progress (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       user_id INTEGER NOT NULL,
       course_id TEXT NOT NULL,
       current_level TEXT NOT NULL DEFAULT 'easy',
       current_question_number INTEGER NOT NULL DEFAULT 1,
       completed INTEGER NOT NULL DEFAULT 0,
       session_questions TEXT,
       bounty_earned INTEGER DEFAULT 0,
       last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (user_id) REFERENCES users(id),
       FOREIGN KEY (course_id) REFERENCES courses(id)
    )''')

    # ── 2. Create bounty_records table ──────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS bounty_records (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       user_id INTEGER NOT NULL,
       course_id TEXT NOT NULL,
       course_name TEXT NOT NULL,
       bounty INTEGER DEFAULT 0,
       completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    # ── 3. Create user_profiles table ────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
       user_id INTEGER PRIMARY KEY,
       display_name TEXT,
       pirate_group TEXT,
       avatar TEXT DEFAULT 'luffy',
       FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    # ── 4. Fix users table: rename password_hash to password if needed ───────
    c.execute('PRAGMA table_info(users)')
    user_cols = [row[1] for row in c.fetchall()]
    if 'password_hash' in user_cols and 'password' not in user_cols:
        c.execute('ALTER TABLE users RENAME COLUMN password_hash TO password')
        print('Renamed password_hash to password')
    elif 'password' not in user_cols:
        print('WARNING: no password column found in users. Please check manually.')

    # ── 5. Insert courses ────────────────────────────────────────────────────
    courses = [
        ('101', 'Python Basics', 'Learn the fundamentals of Python programming.', 'Python'),
        ('102', 'Java Basics', 'Learn the fundamentals of Java programming.', 'Java'),
        ('103', 'HTML & CSS', 'Learn the fundamentals of HTML and CSS.', 'html and css'),
        ('104', 'C Language', 'Learn the fundamentals of C programming.', 'C language'),
    ]
    for course in courses:
        try:
            c.execute('INSERT INTO courses (id, name, description, language) VALUES (?, ?, ?, ?)', course)
        except sqlite3.IntegrityError:
            pass

    # ── 6. Insert questions ──────────────────────────────────────────────────
    easy_questions = [
        ('101-1', 101, 'easy', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to welcome to python', 'welcome to python','Write a Python code to add 100 and 250', '350', 'marine', 'Python'),
        ('101-2', 101, 'easy', 2, 'Write a Python code to check 13 is even or odd', 'odd','Write a Python code to subtract 150 from 200', '50','Write a Python code to find the square of 15', '225', 'marine', 'Python'),
        ('101-3', 101, 'easy', 3, 'Write a Python code to print 12 + 13', '25','Write a Python code to print 14*8', '112','Write a Python code to find the cube of 6', '216', 'marine', 'Python'),
        ('101-4', 101, 'easy', 4, 'Write a Python code to print the largest number where a="15" and b="20".', '20','Write a Python code to divide 100 by 5', '20','Write a Python code to find the largest number between 45 and 18', '45', 'marine', 'Python'),
        ('101-5', 101, 'easy', 5, 'Write a Python code to reverse given string="python"', 'nohtyp','Write a Python code to check whether 45 is positive,negative or zero', 'positive','Write a Python code to find 18 is even or odd', 'even', 'admiral_akainu', 'Python'),
        ('102-1', 102, 'easy', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print welcome to java', 'welcome to java','Write a Java code to add 100 and 73', '173', 'marine', 'Java'),
        ('102-2', 102, 'easy', 2, 'Write a Java code to check 15 is even or odd', 'even','Write a Java code to subtract 25 from 50', '25','Write a Java code to find square of 15', '225', 'marine', 'Java'),
        ('102-3', 102, 'easy', 3, 'Write a Java code to add 45+18', '63','Write a Java code to multiply 14 and 8', '112','Write a Java code to find cube of 6', '216', 'marine', 'Java'),
        ('102-4', 102, 'easy', 4, 'Write a Java code to find the largest of 10 and 14', '14','Write a Java code to divide 100 by 5', '20','Write a Java code to find largest of 18 and 7', '18', 'marine', 'Java'),
        ('102-5', 102, 'easy', 5, 'Write a Java code to reverse the given string="java"', 'avaj','Write a Java code to check whether -13 is positive,negative or zero', 'negative','Write a Java code to 345 is even or odd', 'odd', 'admiral_aokoji', 'Java'),
        ('103-1', 103, 'easy', 1, 'Write a HTML/CSS code to Create a webpage with an <h3> heading saying "Welcome"', '<h3>Welcome</h3>','Write a HTML/CSS code to Create a webpage with an <h2> heading.', '<h2> and </h2>','Write a HTML/CSS code to Create a webpage containing an <h4> heading.', '<h4> and </h4>', 'marine', 'html and css'),
        ('103-2', 103, 'easy', 2, 'Write a HTML/CSS code to Create a webpage containing two paragraphs using <p>.', '<p> and </p>','Write a HTML/CSS code to Create a webpage containing bold text using <b>.', '<b> and </b>','Write a HTML/CSS code to Create a webpage containing three hyperlinks.', '<a>', 'marine', 'html and css'),
        ('103-3', 103, 'easy', 3, 'Write a HTML/CSS code to Create a webpage with an image whose src is "cat.jpg"', '<img and src="cat.jpg"','Write a HTML/CSS code to Create a webpage containing italic text using <i>.', '<i> and </i>','Write a HTML/CSS code to Create a webpage containing two images.', '<img> and <img>', 'marine', 'html and css'),
        ('103-4', 103, 'easy', 4, 'Write a HTML/CSS code to Create a webpage with a hyperlink to https://google.com', '<a and href="https://google.com"','Write a HTML/CSS code to Create a webpage containing a line break using <br>.', '<br>','Write a HTML/CSS code to Create a webpage containing an ordered list with 3 items', '<ol> and <li>', 'marine', 'html and css'),
        ('103-5', 103, 'easy', 5, 'Write a HTML/CSS code to Create a webpage with a horizontal line using <hr>', '<hr>','Write a HTML/CSS code to Create a webpage containing a comment.', '<!-- and -->','Write a HTML/CSS code to create a webpage containing an unordered list with 3 items', '<ul> and <li>', 'akainu', 'html and css'),
        ('104-1', 104, 'easy', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print welcome to c programming', 'welcome to c programming','Write a C code to add 20+20', '40', 'marine', 'C language'),
        ('104-2', 104, 'easy', 2, 'Write a C code to check 22 is even or odd', 'even','Write a C code to subtract 15 from 30', '15','Write a C code to find square of 15', '225', 'marine', 'C language'),
        ('104-3', 104, 'easy', 3, 'Write a C code to add 36+36', '72','Write a C code to multiply 40*3', '120','Write a C code to find cube of 2', '8', 'marine', 'C language'),
        ('104-4', 104, 'easy', 4, 'Write a C code to find the largest number between 25 and 73', '73','Write a C code to divide 500 by 100', '5','Write a C code to find the largest number between 100 and 456', '456', 'marine', 'C language'),
        ('104-5', 104, 'easy', 5, 'Write a C code to reverse a string="luffy"', 'yfful','Write a C code to check whether 10 is positive,negative or zero','positive','Write a C code to check 69 is even or odd', 'odd', 'admiral_kizaru', 'C language'),
    ]

    medium_questions = [
        ('101-6', 101, 'medium', 1, 'Write a Python code to find the square of 9', '81','Write a Python code to print factorial of 6', '720','Write a Python code to calculate the sum of numbers 1 to 50', '1275', 'marine', 'Python'),
        ('101-7', 101, 'medium', 2, 'Write a Python code to find the cube of 5', '125','Write a Python code to print only even numbers from 1 to 20', '2\n4\n6\n8\n10\n12\n14\n16\n18\n20','Write a Python code to print 9 table upto 10', '9\n18\n27\n36\n45\n54\n63\n72\n81\n90', 'marine', 'Python'),
        ('101-8', 101, 'medium', 3, 'Write a Python code to calculate the area of rectangle where length=10 and width=5', '50','Write a Python code to print only odd numbers 1 to 15', '1\n3\n5\n7\n9\n11\n13\n15','Write a Python code to count vowels in "onepiece"', '5', 'marine', 'Python'),
        ('101-9', 101, 'medium', 4, 'Write a Python code to calculate the sum of numbers from 1 to 100', '5050','Write a Python code to count digits in "18451007"', '8','Write a Python code to reverse a string="hello world"', 'dlrow olleh', 'marine', 'Python'),
        ('101-10', 101, 'medium', 5, 'Write a Python code to print multiplication table of 6 upto 6 in format "6x1=6"', '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36','Write a python code to find smallest number in an array=[5, 2, 8, 1, 9]','1','Write a python code to print 31 is prime or not','prime','admiral_aokoji','Python'),
        ('102-6', 102, 'medium', 1, 'Write a Java code to find the square of 45', '2025','Write a Java code to find factorial of 8', '40320','Write a Java code to print sum of numbers from 1 to 10', '55', 'marine', 'Java'),
        ('102-7', 102, 'medium', 2, 'Write a Java code to find cube of 5', '125','Write a Java code to print even numbers only from 20 to 45', '20\n22\n24\n26\n28\n30\n32\n34\n36\n38\n40\n42\n44','Write a Java code to print 5 table upto 10,format="5x1=5"', '5x1=5\n5x2=10\n5x3=15\n5x4=20\n5x5=25\n5x6=30\n5x7=35\n5x8=40\n5x9=45\n5x10=50', 'marine','Java'),
        ('102-8', 102, 'medium', 3, 'Write a Java code to calculate the area of rectangle where length=8 and width=6.', '48','Write a Java code to print only odd numbers from 1 to 15', '1\n3\n5\n7\n9\n11\n13\n15','Write a Java code to count vowels in string="whitebeard"', '5', 'marine', 'Java'),
        ('102-9', 102, 'medium', 4, 'Write a Java code to calculate sum of numbers from 1 to 10', '55','Write a Java code to count digits "1230984567"', '10','Write a Java code to reverse a string="hello world"', 'dlrow olleh', 'marine', 'Java'),
        ('102-10', 102, 'medium', 5, 'Write a Java code to print multiplication table of 6 upto 6,format="6x1=6"', '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36','Write a Java code to find the smallest number in array={2,5,9,3,6,4}', '2','Write a Java code to check whether 17 is prime or not', 'prime', 'admiral_kizaru', 'Java'),
        ('103-6', 103, 'medium', 1, 'Write a HTML/CSS code to Create an unordered list with 4 items', '<ul> and <li>','Write a HTML/CSS code to Create a webpage containing a text area.', '<textarea>','Write a HTML/CSS code to Create a form containing First Name and Last Name text fields.', '<form>and <input', 'marine', 'html and css'),
        ('103-7', 103, 'medium', 2, 'Write a HTML/CSS code to Create an ordered list with 5 items.', '<ol> and <li>','Write a HTML/CSS code to Create a webpage containing a checkbox.', '<input and type="checkbox"','Write a HTML/CSS code to Create a webpage containing an input of type number.', '<input and type="number"', 'marine', 'html and css'),
        ('103-8', 103, 'medium', 3, 'Write a HTML/CSS code to Create a form containing Name and Email input fields.', '<form> and <input','Write a HTML/CSS code to Create a webpage containing two radio buttons.', '<input and type="radio"','Write a HTML/CSS code to Create a webpage containing an input of type date.', '<input and type="date"', 'marine', 'html and css'),
        ('103-9', 103, 'medium', 4, 'Write a HTML/CSS code to Create a webpage containing a button with the text Submit.', '<button>submit</button>','Write a HTML/CSS code to Create a webpage containing a password input field.', '<input and type="password"','Write a HTML/CSS code to Create a webpage containing an input of type color.', '<input and type="color"', 'marine', 'html and css'),
        ('103-10', 103, 'medium', 5, 'Write a HTML/CSS code to Create a webpage containing a table with 2 rows and 3 columns.', '<table> and <tr> and <td>','Write a HTML/CSS code to Create a webpage containing a reset button.', '<input and type="reset"','Write a HTML/CSS code to Create a webpage containing a submit button using button tags', '<button>submit</button>', 'admiral_kizaru', 'html and css'),
        ('104-6', 104, 'medium', 1, 'Write a C code to find the square of 25', '625','Write a C code to find factorial of 5', '120','Write a C code to calculate the sum of numbers from 1 to 10', '55', 'marine', 'C language'),
        ('104-7', 104, 'medium', 2, 'Write a C code to find the cube of 5', '125','Write a C code to print even numbers only from 20 to 45', '20\n22\n24\n26\n28\n30\n32\n34\n36\n38\n40\n42\n44','Write a C code to print 5 table upto 10,format="5x1=5"', '5x1=5\n5x2=10\n5x3=15\n5x4=20\n5x5=25\n5x6=30\n5x7=35\n5x8=40\n5x9=45\n5x10=50', 'marine','C language'),
        ('104-8', 104, 'medium', 3, 'Write a C code to calculate the area of rectangle where length=8 and width=6.', '48','Write a C code to print only odd numbers from 1 to 15', '1\n3\n5\n7\n9\n11\n13\n15','Write a C code to count vowels in string="whitebeard"', '5', 'marine', 'C language'),
        ('104-9', 104, 'medium', 4, 'Write a C code to calculate sum of numbers from 1 to 10', '55','Write a C code to count digits "1230984567"', '10','Write a C code to reverse a string="hello world"', 'dlrow olleh', 'marine', 'C language'),
        ('104-10', 104, 'medium', 5, 'Write a C code to print multiplication table of 6 upto 6,format="6x1=6"', '6x1=6\n6x2=12\n6x3=18\n6x4=24\n6x5=30\n6x6=36','Write a C code to find the smallest number in array={2,5,9,3,6,4}', '2','Write a C code to check whether 17 is prime or not', 'prime', 'admiral_akainu', 'C language'),
    ]

    hard_questions = [
        ('101-11', 101, 'hard', 1, 'Write a Python code to count number of vowels in a string="tony tony chopper"', '4','Write a Python code to check whether 454 is palindrome or not', 'palindrome','Write a Python code to check "madam" is palindrome or not', 'palindrome', 'warlord_hawkeye_mihawk', 'Python'),
        ('101-12', 101, 'hard', 2, 'Write a Python code to check 153 is armstrong or not', 'armstrong','Write a Python code to check 9474 is armstrong or not', 'armstrong','Write a Python code to check 370 is armstrong or not', 'armstrong', 'warlord_doflamingo', 'Python'),
        ('101-13', 101, 'hard', 3, 'Write a Python code to check 121 is palindrome or not', 'palindrome','Write a Python code to print common elements in [2,4,6,8] and [1,2,5,6,9]', '2\n6','Write a Python code to find second largest number in [10,45,7,18,65]', '45', 'kaido', 'Python'),
        ('101-14', 101, 'hard', 4, 'Write a Python code to print the second smallest number in [1,5,8,4,2]', '2','Write a Python code to check whether 43 is prime or not', 'prime','Write a Python code to find common elements in [10,20,30,40] and [10,30,45,18]', '10\n30', 'redhair_shanks', 'Python'),
        ('101-15', 101, 'hard', 5, 'Write a Python code to print multiplication table of 5 with only even numbers upto 10,format="5x2=10"', '5x2=10\n5x4=20\n5x6=30\n5x8=40\n5x10=50','Write a Python code to print multiplication table of 4 with only even numbers upto 10,format="4x2=8"', '4x2=8\n4x4=16\n4x6=24\n4x8=32\n4x10=40','Write a Python code to print multiplication table of 5 with only odd numbers upto 10,format="5x1=5"', '5x1=5\n5x3=15\n5x5=25\n5x7=35\n5x9=45', 'whitebeard', 'Python'),
        ('102-11', 102, 'hard', 1, 'Write a Java code to count number of vowels in the string="google"', '3','Write a Java code to check whether 454 is palindrome or not', 'palindrome','Write a Java code to check whether "madam" is palindrome or not', 'palindrome', 'warlord_hawkeye_mihawk', 'Java'),
        ('102-12', 102, 'hard', 2, 'Write a Java code to check whether 153 is armstrong or not', 'armstrong', 'Write a Java code to check 9474 is armstrong or not', 'armstrong','Write a Java code to check 370 is armstrong or not', 'armstrong', 'warlord_doflamingo', 'Java'),
        ('102-13', 102, 'hard', 3, 'Write a Java code to check whether 121 is palindrome or not', 'palindrome', 'Write a Java code to print common elements in {22,44,33,5,45} and {45,33,10,18}', '45\n33','Write a Java code to find the second largest number in {10,45,18,23,93,7}', '45', 'kaido', 'Java'),
        ('102-14', 102, 'hard', 4, 'Write a Java code to find the second smallest number in {10,45,34,67,32,9}', '10', 'Write a Java code to check whether 71 is prime or not', 'prime','Write a Java code to print common elements in array {10,20,30,40,50} and {10,30,45,18}', '10\n30', 'redhair_shanks', 'Java'),
        ('102-15', 102, 'hard', 5, 'Write a Java code to print multiplication table of 5 with only even numbers upto 10,format="5x2=10"', '5x2=10\n5x4=20\n5x6=30\n5x8=40\n5x10=50','Write a java code to print multiplication table of 4 with only even numbers upto 10,format="4x2=8"', '4x2=8\n4x4=16\n4x6=24\n4x8=32\n4x10=40','Write a java code to print multiplication table of 5 with only odd numbers upto 10,format="5x1=5"', '5x1=5\n5x3=15\n5x5=25\n5x7=35\n5x9=45', 'whitebeard', 'Java'),
        ('103-11', 103, 'hard', 1, 'Write a HTML/CSS code to Create a form containing username, password, and a Login button.', '<form> and <input and <button>', 'Write a HTML/CSS code to Create a webpage containing a dropdown with 4 options.', '<select> and <option>','Write a HTML/CSS code to Create a webpage containing <header>, <nav>, <section>, and <footer>.', '<header> and <nav> and <section> and <footer>', 'warlord_hawkeye_mihawk', 'html and css'),
        ('103-12', 103, 'hard', 2, 'Write a HTML/CSS code to Create a webpage containing an iframe.', '<iframe>', 'Write a HTML/CSS code to Create a webpage containing a table with <caption>.', '<table> and <caption>','Write a HTML/CSS code to Create a table with 3 rows, 3 columns, and a heading row using <th>.', '<table> and <th>', 'warlord_doflamingo', 'html and css'),
        ('103-13', 103, 'hard', 3, 'Write a HTML/CSS code to Create a webpage containing a video player with controls.', '<video> and controls', 'Write a HTML/CSS code to Create a webpage containing an image wrapped inside a hyperlink.', '<a and <img','Write a HTML/CSS code to Create a form containing a required email field and a required password field.', 'type="email" and required and type="password"', 'kaido', 'html and css'),
        ('103-14', 103, 'hard', 4, 'Write a HTML/CSS code to Create a webpage containing an audio player with controls.', '<audio> and controls', 'Write a HTML/CSS code to Create a webpage containing an email input marked as required.', 'type="email" and required','Write a HTML/CSS code to Create a webpage containing both audio and video players with controls.', '<audio and <video and controls', 'redhair_shanks', 'html and css'),
        ('103-15', 103, 'hard', 5, 'Write a HTML/CSS code to Create a webpage using the semantic tags <header>, <main>, and <footer>.', '<header> and <main> and <footer>', 'Write a HTML/CSS code to Create a webpage containing a form with Name, Email, Password, and a Submit button.','<form> and type="email" and type="password" and <button>','Write a HTML/CSS code to Create a webpage containing an image with width="200", height="200", and an alt attribute.', '<img and height="200" and width="200" and alt=', 'whitebeard', 'html and css'),
        ('104-11', 104, 'hard', 1, 'Write a C code to count number of vowels in the string="google"', '3','Write a C code to check whether 454 is palindrome or not', 'palindrome','Write a C code to check whether "madam" is palindrome or not', 'palindrome', 'warlord_hawkeye_mihawk', 'C language'),
        ('104-12', 104, 'hard', 2, 'Write a C code to check whether 153 is armstrong or not', 'armstrong', 'Write a C code to check 9474 is armstrong or not', 'armstrong','Write a C code to check 370 is armstrong or not', 'armstrong', 'warlord_doflamingo', 'C language'),
        ('104-13', 104, 'hard', 3, 'Write a C code to check whether 121 is palindrome or not', 'palindrome', 'Write a C code to print common elements in {22,44,33,5,45} and {45,33,10,18}', '45\n33','Write a C code to find the second largest number in {10,45,18,23,93,7}', '45', 'kaido', 'C language'),
        ('104-14', 104, 'hard', 4, 'Write a C code to find the second smallest number in {10,45,34,67,32,9}', '10', 'Write a C code to check whether 71 is prime or not', 'prime','Write a C code to print common elements in array {10,20,30,40,50} and {10,30,45,18}', '10\n30', 'redhair_shanks', 'C language'),
        ('104-15', 104, 'hard', 5, 'Write a C code to print multiplication table of 5 with only even numbers upto 10,format="5x2=10"', '5x2=10\n5x4=20\n5x6=30\n5x8=40\n5x10=50','Write a C code to print multiplication table of 4 with only even numbers upto 10,format="4x2=8"', '4x2=8\n4x4=16\n4x6=24\n4x8=32\n4x10=40','Write a C code to print multiplication table of 5 with only odd numbers upto 10,format="5x1=5"', '5x1=5\n5x3=15\n5x5=25\n5x7=35\n5x9=45', 'whitebeard', 'C language'),
    ]

    all_questions = easy_questions + medium_questions + hard_questions
    inserted = 0
    for q in all_questions:
        try:
            c.execute('''INSERT INTO questions
                (id, course_id, level, question_number,
                 question_text_1, expected_output_1,
                 question_text_2, expected_output_2,
                 question_text_3, expected_output_3,
                 opponent_name, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', q)
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

    print(f'Migration complete!')
    print(f'  Inserted {inserted} questions')
    print(f'  Tables: users, courses, questions, progress, bounty_records, user_profiles')

if __name__ == '__main__':
    migrate_and_seed()
