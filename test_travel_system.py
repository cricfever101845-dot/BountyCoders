import unittest
import json
import sqlite3
import app

class TestShipTravelSystem(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_game_page_renders_ship_travel_system(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'luffy'

        resp = self.client.get('/game/101')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # 1. Map viewport & 16:9 stage
        self.assertIn('id="map-viewport"', html)
        self.assertIn('id="map-stage"', html)
        self.assertIn('id="map-image"', html)

        # 2. Transparent Thousand Sunny ship cutout & container
        self.assertIn('id="ship-container"', html)
        self.assertIn('id="ship-sprite"', html)
        self.assertIn('/static/media/sunny.png', html)

        # 3. All 3 map references
        self.assertIn('/static/media/easy.jpeg', html)
        self.assertIn('/static/media/medium.jpeg', html)
        self.assertIn('/static/media/hard.jpeg', html)

        # 4. Obsolete videos removed
        self.assertNotIn('easy.mp4', html)
        self.assertNotIn('medium.mp4', html)
        self.assertNotIn('hard.mp4', html)

        # 5. Transitions preserved
        self.assertIn('/static/media/grandline.mp4', html)
        self.assertIn('/static/media/new world.mp4', html)

        # 6. Continue button & navigation coordination
        self.assertIn('id="continue-btn"', html)
        self.assertIn('continueToNextLeg()', html)

    def test_start_session_progression(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'luffy'

        resp = self.client.post('/api/start_session', json={
            'course_id': '101',
            'force_new': True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['current_level'], 'easy')
        self.assertEqual(data['current_question_number'], 1)
        self.assertIn('easy', data['session_questions'])
        self.assertIn('medium', data['session_questions'])
        self.assertIn('hard', data['session_questions'])

    def test_full_progression_cycle_1_to_15(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'luffy'

        # Start fresh course
        resp = self.client.post('/api/start_session', json={'course_id': '101', 'force_new': True})
        self.assertEqual(resp.status_code, 200)

        # 1. Complete East Blue (Levels 1 to 5)
        for q in range(1, 6):
            resp = self.client.post('/api/submit_answer', json={
                'course_id': '101',
                'level': 'easy',
                'question_number': q,
                'code': 'print("OK")',
                'expected_output': 'OK',
                'language': 'Python'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json()['correct'])

        # Progress should now be at Grand Line (medium), question 1 (overall Level 6)
        conn = app.get_db()
        c = conn.cursor()
        c.execute('SELECT current_level, current_question_number, completed FROM progress WHERE user_id = 1 AND course_id = "101" AND completed = 0')
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['current_level'], 'medium')
        self.assertEqual(row['current_question_number'], 1)

        # 2. Complete Grand Line (Levels 6 to 10)
        for q in range(1, 6):
            resp = self.client.post('/api/submit_answer', json={
                'course_id': '101',
                'level': 'medium',
                'question_number': q,
                'code': 'print("OK")',
                'expected_output': 'OK',
                'language': 'Python'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json()['correct'])

        # Progress should now be at New World (hard), question 1 (overall Level 11)
        conn = app.get_db()
        c = conn.cursor()
        c.execute('SELECT current_level, current_question_number, completed FROM progress WHERE user_id = 1 AND course_id = "101" AND completed = 0')
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['current_level'], 'hard')
        self.assertEqual(row['current_question_number'], 1)

        # 3. Complete New World (Levels 11 to 15)
        for q in range(1, 6):
            resp = self.client.post('/api/submit_answer', json={
                'course_id': '101',
                'level': 'hard',
                'question_number': q,
                'code': 'print("OK")',
                'expected_output': 'OK',
                'language': 'Python'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json()['correct'])

        # Course should now be marked completed = 1
        conn = app.get_db()
        c = conn.cursor()
        c.execute('SELECT current_level, current_question_number, completed FROM progress WHERE user_id = 1 AND course_id = "101" ORDER BY last_updated DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        self.assertEqual(row['completed'], 1)

        # Completion route renders King of the Pirates page
        resp = self.client.get('/completion/101')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('King of the Pirates', resp.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
