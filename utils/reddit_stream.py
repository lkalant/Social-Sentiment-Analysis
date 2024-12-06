# utils/reddit_stream.py

import time
import re
from config import MAX_POSTS
from utils.kafka_producer import KafkaProducerHandler
import prawcore

def reddit_stream(reddit, subreddits, keywords, kafka_producer_handler, update_content_callback, stop_event):
    subreddit_str = '+'.join(subreddits)
    subreddit = reddit.subreddit(subreddit_str)
    compiled_keywords = [re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE) for keyword in keywords] if keywords else []
    processed_comments = set()

    try:
        # First, fetch existing comments
        for comment in subreddit.comments(limit=None):
            if stop_event.is_set():
                print("Streaming thread received stop signal.")
                break

            process_comment(comment, compiled_keywords, processed_comments, kafka_producer_handler, update_content_callback)
            time.sleep(0.1)  # Reduced sleep time for initial fetching

        # Stream new comments
        while not stop_event.is_set():
            for comment in subreddit.stream.comments(skip_existing=True, pause_after=1):
                if stop_event.is_set():
                    print("Streaming thread received stop signal.")
                    break

                if comment is None:
                    continue

                process_comment(comment, compiled_keywords, processed_comments, kafka_producer_handler, update_content_callback)
                time.sleep(1)

    except Exception as e:
        print(f"Error in Reddit stream: {e}")

def process_comment(comment, compiled_keywords, processed_comments, kafka_producer_handler, update_content_callback):
    comment_id = comment.id
    if comment_id in processed_comments:
        return
    processed_comments.add(comment_id)

    body = comment.body
    author = comment.author.name if comment.author else "Unknown"
    subreddit_name = comment.subreddit.display_name
    created_utc = comment.created_utc
    permalink = comment.permalink

    is_analyzed = any(keyword.search(body) for keyword in compiled_keywords)

    data_for_ui = {
        'subreddit': subreddit_name,
        'author': author,
        'body': body,
        'created_utc': created_utc,
        'id': comment_id,
        'permalink': f"https://www.reddit.com{permalink}",
        'is_analyzed': is_analyzed
    }

    # Update UI with Reddit comment
    update_content_callback(data_for_ui)

    if is_analyzed:
        data = {
            'subreddit': subreddit_name,
            'author': author,
            'body': body,
            'created_utc': created_utc,
            'id': comment_id,
            'permalink': f"https://www.reddit.com{permalink}"
        }
        topic_name = f"reddit_{subreddit_name.lower()}"
        kafka_producer_handler.send_message(topic_name, data)
        print(f"Sent to Kafka topic '{topic_name}': {comment_id}")
