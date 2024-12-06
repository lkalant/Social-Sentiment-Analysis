# utils/kafka_consumer.py

import threading
import json
from kafka import KafkaConsumer
from config import KAFKA_BOOTSTRAP_SERVERS
from utils.sentiment_analysis import analyze_sentiment

class SentimentConsumer(threading.Thread):
    def __init__(self, selected_subreddits, keyword, update_callback, stop_event):
        super().__init__()
        self.selected_subreddits = selected_subreddits
        self.keyword = keyword.lower()
        self.update_callback = update_callback
        self.consumer = None
        self.stop_event = stop_event

    def run(self):
        topics = [f"reddit_{sub.lower()}" for sub in self.selected_subreddits]
        try:
            self.consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                group_id='sentiment-analysis-group',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            print(f"Consumer subscribed to topics: {topics}")

            while not self.stop_event.is_set():
                message_batch = self.consumer.poll(timeout_ms=1000)
                for _, messages in message_batch.items():
                    for message in messages:
                        data = message.value
                        body = data['body']
                        subreddit_name = data['subreddit']
                        if self.keyword in body.lower():
                            sentiment = analyze_sentiment(body)
                            self.update_callback(subreddit_name, sentiment)
        except Exception as e:
            print(f"Error in SentimentConsumer: {e}")

    def stop(self):
        self.stop_event.set()
        if self.consumer:
            self.consumer.close()
        print("Sentiment consumer stopped.")
