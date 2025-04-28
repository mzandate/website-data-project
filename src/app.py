from flask import Flask, jsonify, render_template, request, Response
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from prometheus_client import Counter, Histogram, generate_latest
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time

# App setup

import subprocess

subprocess.run(["playwright", "install"], check=True)

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

# Scraper function
def scrape_metacritic(count=None):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        games = []
        page_num = 1

        while True:
            url = f"https://www.metacritic.com/browse/game/?releaseYearMin=1958&releaseYearMax=2025&page={page_num}"
            page.goto(url, timeout=60000)
            page.wait_for_selector('.c-finderProductCard')

            soup = BeautifulSoup(page.content(), 'html.parser')
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

        browser.close()
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

# Request hooks
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


##scapres all games from metacritic and store them in the database
@app.route('/all')
def scrape_all_games():
    try:
        games = scrape_metacritic(count=1000)

        Game.query.delete()
        db.session.commit()

        for g in games:
            game = Game(title=g['title'], score=g['score'], link=g['link'])
            db.session.add(game)
        db.session.commit()

        return jsonify({'message': f'Successfully added {len(games)} games to the database.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/games_db')
def list_games_db():
    games = Game.query.all()
    result = [{'title': g.title, 'score': g.score, 'link': g.link} for g in games]
    return jsonify(result)

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
