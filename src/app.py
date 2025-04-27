from flask import Flask, jsonify, render_template, request, Response
from prometheus_client import Counter, Histogram, generate_latest, Gauge
import time
from bs4 import BeautifulSoup
from flask_apscheduler import APScheduler
from playwright.sync_api import sync_playwright
from flask_sqlalchemy import SQLAlchemy
import pika
import json




app = Flask(__name__)


#database config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///games.db'  # Simple SQLite DB file
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#methrics checks/health checks
REQUEST_COUNT = Counter('app_requests_total', 'Total number of requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('app_request_latency_seconds', 'Request latency', ['endpoint'])
GAME_COUNT = Gauge('game_count_total', 'Total number of games in the database')


# it runs onces a wekk to update database 
def job_store_all_games():
    print("Running weekly scraper job...")
    games = scrape_metacritic(count=9999)
    Game.query.delete()
    for g in games:
        db.session.add(Game(title=g['title'], score=g['score'], link=g['link']))
    db.session.commit()

    # Update gauge after weekly scrape
    GAME_COUNT.set(Game.query.count())

    print(f"{len(games)} games added.")


class Config:
    SCHEDULER_API_ENABLED = True


# Initialize the APScheduler and set the configuration
# for the Flask app
app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()
    
scheduler.add_job(
    id='weekly_game_scrape',
    func=job_store_all_games,
    trigger='interval',
    days=7
)
#databse model for games
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    score = db.Column(db.String(10))
    link = db.Column(db.String(512))

    def __repr__(self):
        return f'<Game {self.title}>'

#this method scapes all the metacrits games from teh webiste and reutrns as a dict
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
                print(f"Title: {title}, Score: {score}, Link: {link}")  # Debugging line
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



#home page route
@app.route('/')
def home():
    count = request.args.get('count', default=0, type=int)
    games = Game.query.limit(count).all() if count > 0 else []
    return render_template('index.html', games=games)


# health check for checkign teh enodpoings 
@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype='text/plain')

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    REQUEST_COUNT.labels(method=request.method, endpoint=request.path).inc()
    REQUEST_LATENCY.labels(endpoint=request.path).observe(time.time() - request.start_time)
    return response


@app.route('/games')
def show_games():
    count = request.args.get('count', default=10, type=int)
    games = Game.query.limit(count).all()
    return render_template('index.html', games=games)

## this is the route that does teh scraping and sends teh data to teh worker and then to teh database
@app.route('/all')
def scrape_all_games():
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue='scrape_queue', durable=True)

        message = json.dumps({'action': 'scrape_all'})
        channel.basic_publish(
            exchange='',
            routing_key='scrape_queue',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()

        return jsonify({'message': 'Scrape job sent to worker!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    
## to see all the database games in json format 
@app.route('/games_db')
def list_games_db():
    games = Game.query.all()
    result = [{'title': g.title, 'score': g.score, 'link': g.link} for g in games]
    return jsonify(result)    

## route for json testing 
@app.route('/api/games')
def get_games_api():
    count = request.args.get('count', default=10, type=int)
    games = scrape_metacritic(count)
    return jsonify(games)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)