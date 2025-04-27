import unittest
from app import scrape_metacritic  

class TestMetacritic(unittest.TestCase):
    

    # simple test to make sure that we are getting a game form teh website
    def test_first_game(self):
        games = scrape_metacritic(1)
        self.assertEqual(len(games), 1, "Should return exactly one game")

        game = games[0]
        self.assertIn('title', game)
        self.assertIn('score', game)
        self.assertIn('link', game)

        self.assertIsInstance(game['title'], str)
        self.assertIsInstance(game['score'], str)
        self.assertTrue(game['link'].startswith("https://www.metacritic.com"))

        print("First game title:", game['title'])  

if __name__ == '__main__':
    unittest.main()
