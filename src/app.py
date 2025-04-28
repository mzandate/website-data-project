import os
import time
from flask import Flask, jsonify, render_template, request, Response
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from prometheus_client import Counter, Histogram, generate_latest
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service


# Flask app setup
app = Flask(__name__)

# Database config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///games.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Metrics
REQUEST_COUNT = Counter('app_requests_total', 'Total number of requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('app_request_latency_seconds', 'Request latency', ['endpoint'])

# APScheduler config
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Game model
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    score = db.Column(db.String(10))
    link = db.Column(db.String(512))

    def __repr__(self):
        return f'<Game {self.title}>'

# Scraper function using Selenium
def scrape_metacritic(count=None):
    options = Options()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    options.binary_location = chrome_bin

    chrome_service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=chrome_service, options=options)

    games = []
    page_num = 0

    try:
        while True:
            url = f"https://www.metacritic.com/browse/game/?releaseYearMin=1958&releaseYearMax=2025&page={page_num}"
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".c-finderProductCard"))
                )
            except Exception:
                # No more cards found or timeout - stop scraping
                break

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            cards = soup.select('.c-finderProductCard')

            if not cards:
                break

            for card in cards:
                title_el = card.select_one('.c-finderProductCard_titleHeading span:nth-of-type(2)')
                score_el = card.select_one('.c-finderProductCard_score .c-siteReviewScore span')
                link_el = card.select_one('a.c-finderProductCard_container')

                title = title_el.get_text(strip=True) if title_el else 'N/A'
                score = score_el.get_text(strip=True) if score_el else 'N/A'
                link = 'https://www.metacritic.com' + link_el['href'] if link_el and link_el.has_attr('href') else 'N/A'

                games.append({
                    'title': title,
                    'score': score,
                    'link': link
                })

                if count is not None and len(games) >= count:
                    break

            if count is not None and len(games) >= count:
                break

            page_num += 1
    finally:
        driver.quit()

    return games

# Scheduled job (runs once a week)
def job_store_all_games():
    print("Running weekly scraper job...")
    games = scrape_metacritic(count=9999)
    Game.query.delete()
    for g in games:
        db.session.add(Game(title=g['title'], score=g['score'], link=g['link']))
    db.session.commit()
    print(f"{len(games)} games added.")

scheduler.add_job(
    id='weekly_game_scrape',
    func=job_store_all_games,
    trigger='interval',
    days=7
)

# Request hooks for metrics
@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    REQUEST_COUNT.labels(method=request.method, endpoint=request.path).inc()
    REQUEST_LATENCY.labels(endpoint=request.path).observe(time.time() - request.start_time)
    return response

# Routes
@app.route('/')
def home():
    count = request.args.get('count', default=0, type=int)
    games = Game.query.limit(count).all() if count > 0 else []
    return render_template('index.html', games=games)

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/games')
def show_games():
    count = request.args.get('count', default=10, type=int)
    games = Game.query.limit(count).all()
    return render_template('index.html', games=games)

@app.route('/all')
def scrape_all_games():
    try:
        games = scrape_metacritic(count=40)

        Game.query.delete()
        db.session.commit()

        for g in games:
            game = Game(title=g['title'], score=g['score'], link=g['link'])
            db.session.add(game)
        db.session.commit()

        return jsonify({'message': f'Successfully added {len(games)} games to the database.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
## route to show games in database 
@app.route('/games_db')
def list_games_db():
    games = Game.query.all()
    result = [{'title': g.title, 'score': g.score, 'link': g.link} for g in games]
    return jsonify(result)
## api route for testing 
@app.route('/api/games')
def get_games_api():
    count = request.args.get('count', default=10, type=int)
    games = scrape_metacritic(count)
    return jsonify(games)

# Main
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
