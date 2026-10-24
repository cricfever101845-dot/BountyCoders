import unittest
import json
from app import app, select_top_bounty_posters, get_db

class TestBountyCollection(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def test_unauthenticated_access(self):
        resp = self.client.get('/api/bounty_collection')
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_authenticated_access(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'testpirate'

        resp = self.client.get('/api/bounty_collection')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        # Check user payload
        self.assertIn('user', data)
        user = data['user']
        self.assertEqual(user['username'], 'testpirate')
        self.assertIn('avatar_url', user)
        self.assertIn('pirate_group', user)

        # Check courses
        self.assertIn('courses', data)
        courses = data['courses']
        for expected_key in ['python', 'java', 'html', 'c']:
            self.assertIn(expected_key, courses)
            cinfo = courses[expected_key]
            self.assertIn('posters', cinfo)
            self.assertIn('total_plays', cinfo)
            self.assertLessEqual(len(cinfo['posters']), 5)

        # User 1 completed only Python, NOT C, Java, or HTML
        self.assertGreater(courses['python']['total_plays'], 0)
        self.assertEqual(courses['c']['total_plays'], 0)
        self.assertEqual(len(courses['c']['posters']), 0)
        self.assertEqual(courses['java']['total_plays'], 0)
        self.assertEqual(len(courses['java']['posters']), 0)
        self.assertEqual(courses['html']['total_plays'], 0)
        self.assertEqual(len(courses['html']['posters']), 0)

    def test_selection_rules_case_a(self):
        # Case A: fewer than 5 records
        records = [
            {'id': 1, 'bounty': 2000000, 'completed_at': '2026-10-01 10:00:00'},
            {'id': 2, 'bounty': 5000000, 'completed_at': '2026-10-02 10:00:00'},
            {'id': 3, 'bounty': 2000000, 'completed_at': '2026-10-03 10:00:00'},
        ]
        selected = select_top_bounty_posters(records)
        self.assertEqual(len(selected), 3)
        self.assertEqual([r['bounty'] for r in selected], [5000000, 2000000, 2000000])

    def test_selection_rules_case_c_more_than_5_distinct(self):
        # Case C: 1000, 5000, 3000, 5000, 2000, 7000, 3000, 7000, 7000
        amounts = [1000, 5000, 3000, 5000, 2000, 7000, 3000, 7000, 7000]
        records = [{'id': i, 'bounty': b, 'completed_at': f'2026-10-01 0{i}:00:00'} for i, b in enumerate(amounts)]
        selected = select_top_bounty_posters(records)
        self.assertEqual(len(selected), 5)
        self.assertEqual([r['bounty'] for r in selected], [7000, 5000, 3000, 2000, 1000])

    def test_selection_rules_case_c_less_than_5_distinct(self):
        # Only 3 distinct amounts: 7000, 5000, 2000 with duplicates
        amounts = [7000, 7000, 5000, 5000, 5000, 2000]
        records = [{'id': i, 'bounty': b, 'completed_at': f'2026-10-01 0{i}:00:00'} for i, b in enumerate(amounts)]
        selected = select_top_bounty_posters(records)
        self.assertEqual(len(selected), 5)
        self.assertEqual([r['bounty'] for r in selected], [7000, 7000, 5000, 5000, 2000])

    def test_home_page_rendered_elements(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'testpirate'

        resp = self.client.get('/home')
        self.assertEqual(resp.status_code, 200)
        content = resp.get_data(as_text=True)
        self.assertIn('id="bounty-modal"', content)
        self.assertIn('selectBountyCourse', content)
        self.assertIn('bounty-course-tab', content)
        self.assertIn('bounty_template.png', content)
        self.assertIn('prevBountyPoster()', content)
        self.assertIn('nextBountyPoster()', content)

    def test_single_bounty_per_course_completion(self):
        # Using a dedicated test user (e.g. user_id = 999)
        test_uid = 999
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM bounty_records WHERE user_id = ?', (test_uid,))
        c.execute('DELETE FROM progress WHERE user_id = ?', (test_uid,))
        c.execute('INSERT OR IGNORE INTO users (id, username, email, password, total_bounty) VALUES (?, ?, ?, ?, 0)',
                  (test_uid, 'solopirate', 'solopirate@test.com', 'dummy'))
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess['user_id'] = test_uid
            sess['username'] = 'solopirate'

        # Start session for course 104 (C)
        self.client.post('/api/start_session', json={'course_id': '104', 'force_new': True})

        # Answer question 15 (hard q 5)
        self.client.post('/api/submit_answer', json={
            'course_id': '104',
            'level': 'hard',
            'question_number': 5,
            'code': '#include <stdio.h>\nint main(){printf("OK");return 0;}',
            'expected_output': 'OK',
            'language': 'C'
        })

        # Client also invokes api_complete_course upon animation finish
        self.client.post('/api/complete_course', json={'course_id': '104'})

        # Verify only 1 bounty poster is returned
        resp = self.client.get('/api/bounty_collection?course=c')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        c_posters = data['course']['posters']
        self.assertEqual(len(c_posters), 1)
        self.assertEqual(data['course']['total_plays'], 1)

        # Clean up
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM bounty_records WHERE user_id = ?', (test_uid,))
        c.execute('DELETE FROM progress WHERE user_id = ?', (test_uid,))
        c.execute('DELETE FROM users WHERE id = ?', (test_uid,))
        conn.commit()
        conn.close()

if __name__ == '__main__':
    unittest.main()
