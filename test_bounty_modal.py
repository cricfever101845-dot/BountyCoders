import unittest
import json
from app import app, select_top_bounty_posters

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

if __name__ == '__main__':
    unittest.main()
