import sqlite3
from datetime import datetime

def insert_courses_and_questions():
    conn = sqlite3.connect('bountycoders.db')
    c = conn.cursor()

    # Insert courses
    courses = [
        (101, 'Python Basics', 'Learn the fundamentals of Python programming.', 'Python'),
        (102, "java basics", "Learn the fundamentals of Java programming.", "Java"),
        (103, "html & css", "Learn the fundamentals", "html and css"),
        (104, "c language", "Learn the fundamentals of C programming.", "C")
    ]

    for course in courses:
            try:
                c.execute('INSERT INTO courses (id,name, description, language) VALUES (?, ?, ?, ?)', course)
            except sqlite3.IntegrityError:
                pass

    easy_questions = [
        ('101-1', 101, 'easy', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to welcome to python', 'welcome to python','Write a Python code to add 100 and 250', '350', 'marine', 'Python'),
        ('101-2', 101, 'easy', 1, 'Write a Python code to check 13 is even or odd', 'odd','Write a Python code to subtract 150 from 200', '50','Write a Python code to find the square of 15', '225', 'marine', 'Python'),
        ('101-3', 101, 'easy', 1, 'Write a Python code to print 12 + 13', '25','Write a Python code to print 14*8', '112','Write a Python code to find the cube of 6', '216', 'marine', 'Python'),
        ('101-4', 101, 'easy', 1, 'Write a Python code to print the largest number where a="15" and b="20".', '20','Write a Python code to divide 100 by 5', '20','Write a Python code to find the largest number between 45 and 18', '45', 'marine', 'Python'),
        ('101-5', 101, 'easy', 1, 'Write a Python code to reverse given string="python"', 'nohtyp','Write a Python code to check whether 45 is positive,negative or zero', 'positive','Write a Python code to find 18 is even or odd', 'even', 'admiral_akainu', 'Python'),
        ('102-1', 102, 'easy', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print welcome to java', 'welcome to java','Write a Java code to add 100 and 73', '173', 'marine', 'Java'),
        ('102-2', 102, 'easy', 1, 'Write a Java code to check 15 is even or odd', 'even','Write a Java code to subtract 25 from 50', '25','Write a Java code to find square of 15', '225', 'marine', 'Java'),
        ('102-3', 102, 'easy', 1, 'Write a Java code to add 45+18', '63','Write a Java code to multiply 14 and 8', '112','Write a Java code to find cube of 6', '216', 'marine', 'Java'),
        ('102-4', 102, 'easy', 1, 'Write a Java code to find the largest of 10 and 14', '14','Write a Java code to divide 100 by 5', '20','Write a Java code to largest of 18 and 7', '18', 'marine', 'Java'),
        ('102-5', 102, 'easy', 1, 'Write a Java code to reverse the given string="java"', 'avaj','Write a Java code to check whether -13 is positive,negative or zero', 'negative','Write a Java code to 345 is even or odd', 'odd', 'admiral_aokiji', 'Java'),
        ('103-1', 103, 'easy', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to ', 'hello world','Write a HTML/CSS code to ', 'hello world', 'marine', 'html and css'),
        ('103-2', 103, 'easy', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to ', 'hello world','Write a HTML/CSS code to ', 'hello world', 'marine', 'html and css'),
        ('103-3', 103, 'easy', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to ', 'hello world','Write a HTML/CSS code to ', 'hello world', 'marine', 'html and css'),
        ('103-4', 103, 'easy', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to ', 'hello world','Write a HTML/CSS code to ', 'hello world', 'marine', 'html and css'),
        ('103-5', 103, 'easy', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to ', 'hello world','Write a HTML/CSS code to ', 'hello world', 'marine', 'html and css'),
        ('104-1', 104, 'easy', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print welcome to c programming', 'welcome to c programming','Write a C code to add 20+20', '40', 'marine', 'C language'),
        ('104-2', 104, 'easy', 1, 'Write a C code to check 22 is even or odd', 'even','Write a C code to subtract 15 from 30', '15','Write a C code to find square of 15', '255', 'marine', 'C language'),
        ('104-3', 104, 'easy', 1, 'Write a C code to add 36+36', '72','Write a C code to multiply 40*3', '120','Write a C code to find cube of 2', '8', 'marine', 'C language'),
        ('104-4', 104, 'easy', 1, 'Write a C code to find the largest number 25 and 73', '73','Write a C code to divide 500 by 100', '5','Write a C code to find the largest number 100 and 456', '456', 'marine', 'C language'),
        ('104-5', 104, 'easy', 1, 'Write a C code to reverse a string="luffy"', 'yfful','Write a C code to check whether 10 is positive,negative or zero','positive','Write a C code to check 69 is even or odd', 'odd', 'admiral_kizaru', 'C language'),
        ]

    medium_questions=[
        ('101-6', 101, 'medium', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-7', 101, 'medium', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-8', 101, 'medium', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-9', 101, 'medium', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-10', 101, 'medium', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('102-6', 102, 'medium', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-7', 102, 'medium', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-8', 102, 'medium', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-9', 102, 'medium', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-10',102, 'medium', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('103-6', 103, 'medium', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-7', 103, 'medium', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-8', 103, 'medium', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-9', 103, 'medium', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-10', 103, 'medium', 1, 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('104-6', 104, 'medium', 1, 'Write a C code to print hello.', 'hello world','Write a C code to print hello世界.', 'hello world','Write a C code to print hello世界.', 'hello world', 'marine', 'C language'),
        ('104-7', 104, 'medium', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-8', 104, 'medium', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-9', 104, 'medium', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-10', 104, 'medium', 1, 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ]
   
    hard_questions = [
        ('101-11', 101, 'hard', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-12', 101, 'hard', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-13', 101, 'hard', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-14', 101, 'hard', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('101-15', 101, 'hard', 1, 'Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world','Write a Python code to print hello world.', 'hello world', 'marine', 'Python'),
        ('102-11', 102, 'hard', 1, 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-12', 102, 'hard', 1, 'Write a Java code to print hello world.', 'hello world', 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-13', 102, 'hard', 1, 'Write a Java code to print hello world.', 'hello world', 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-14', 102, 'hard', 1, 'Write a Java code to print hello world.', 'hello world', 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('102-15', 102, 'hard', 1, 'Write a Java code to print hello world.', 'hello world', 'Write a Java code to print hello world.', 'hello world','Write a Java code to print hello world.', 'hello world', 'marine', 'Java'),
        ('103-11', 103, 'hard', 1, 'Write a HTML/CSS code to print hello world.', 'hello world', 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-12', 103, 'hard', 1, 'Write a HTML/CSS code to print hello world.', 'hello world', 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-13', 103, 'hard', 1, 'Write a HTML/CSS code to print hello world.', 'hello world', 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-14', 103, 'hard', 1, 'Write a HTML/CSS code to print hello world.', 'hello world', 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('103-15', 103, 'hard', 1, 'Write a HTML/CSS code to print hello world.', 'hello world', 'Write a HTML/CSS code to print hello world.', 'hello world','Write a HTML/CSS code to print hello world.', 'hello world', 'marine', 'html and css'),
        ('104-11', 104, 'hard', 1, 'Write a C code to print hello world.', 'hello world', 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-12', 104, 'hard', 1, 'Write a C code to print hello world.', 'hello world', 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-13', 104, 'hard', 1, 'Write a C code to print hello world.', 'hello world', 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-14', 104, 'hard', 1, 'Write a C code to print hello world.', 'hello world', 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
        ('104-15', 104, 'hard', 1, 'Write a C code to print hello world.', 'hello world', 'Write a C code to print hello world.', 'hello world','Write a C code to print hello world.', 'hello world', 'marine', 'C language'),
]

    for question in easy_questions + medium_questions + hard_questions:
        try:
            c.execute('''INSERT INTO questions (id, course_id, level, question_number, question_text_1, expected_output_1, question_text_2, expected_output_2, question_text_3, expected_output_3, opponent_name, language)
                         VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', question)
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

    if __name__ == "__main__":
      insert_courses_and_questions()