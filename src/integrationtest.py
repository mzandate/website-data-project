import unittest
from app import app

class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_api_games_route(self):
        response = self.app.get('/api/games')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn('title', data[0])

    def test_api_games_custom_count(self):
        response = self.app.get('/api/games?count=3')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), 3)

if __name__ == '__main__':
    unittest.main()