# utils/kafka_setup.py

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from config import KAFKA_BOOTSTRAP_SERVERS

def create_kafka_topic(topic_name, num_partitions=1, replication_factor=1):
    admin_client = KafkaAdminClient(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id='reddit-sentiment-app'
    )
    topic = NewTopic(
        name=topic_name,
        num_partitions=num_partitions,
        replication_factor=replication_factor
    )
    try:
        admin_client.create_topics(new_topics=[topic], validate_only=False)
        print(f"Kafka topic '{topic_name}' created successfully.")
    except TopicAlreadyExistsError:
        print(f"Kafka topic '{topic_name}' already exists.")
    except Exception as e:
        print(f"Failed to create Kafka topic '{topic_name}': {e}")
    finally:
        admin_client.close()

def setup_kafka_topics(subreddits):
    for subreddit in subreddits:
        topic_name = f"reddit_{subreddit.lower()}"
        create_kafka_topic(topic_name)
