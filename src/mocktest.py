import unittest
from unittest.mock import patch
from app import app
## test using fake data 
class IntegrationTestWithMock(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch('app.scrape_metacritic')
    def test_mocked_api_games_route(self, mock_scrape):
        mock_scrape.return_value = [
            {
                'title': 'Fake Game 1',
                'score': '95',
                'link': 'https://www.metacritic.com/fake-game-1'
            },
            {
                'title': 'Fake Game 2',
                'score': '90',
                'link': 'https://www.metacritic.com/fake-game-2'
            }
        ]
        response = self.client.get('/api/games?count=2')
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['title'], 'Fake Game 1')
        self.assertEqual(data[1]['score'], '90')

if __name__ == '__main__':
    unittest.main()
