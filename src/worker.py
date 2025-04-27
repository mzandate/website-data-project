import pika
import json
from app import app, db, Game  # import models you need

def callback(ch, method, properties, body):
    data = json.loads(body)
    action = data.get('action')

    if action == 'scrape_all':
        print("Starting scrape_all job...")
        from app import scrape_metacritic  # import here to avoid circular issues

        games = scrape_metacritic(count=1000)

        with app.app_context():
            Game.query.delete()
            db.session.commit()

            for g in games:
                game = Game(title=g['title'], score=g['score'], link=g['link'])
                db.session.add(game)
            db.session.commit()

        print(f"Scrape_all job done. {len(games)} games saved.")
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    with app.app_context():
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue='scrape_queue', durable=True)

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue='scrape_queue', on_message_callback=callback)

        print(' [*] Waiting for messages. To exit press CTRL+C')
        channel.start_consuming()

if __name__ == '__main__':
    main()
