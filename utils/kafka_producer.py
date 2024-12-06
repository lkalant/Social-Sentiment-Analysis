# utils/kafka_producer.py

from kafka import KafkaProducer
import json
from config import KAFKA_BOOTSTRAP_SERVERS

class KafkaProducerHandler:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all'
        )

    def send_message(self, topic_name, data):
        self.producer.send(topic_name, value=data)

    def close(self):
        self.producer.close()
