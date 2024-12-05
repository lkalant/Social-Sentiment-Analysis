import threading
import time
import re
import json
from tkinter import *
from tkinter import ttk, scrolledtext
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
import praw
import prawcore  # For subreddit validation
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque
import nltk
import pandas as pd
from nltk.sentiment.vader import SentimentIntensityAnalyzer
nltk.download('vader_lexicon')

# Initialize the VADER sentiment analyzer
vader_analyzer = SentimentIntensityAnalyzer()

# Ensure Matplotlib can be used with Tkinter
matplotlib.use('TkAgg')

# --------------------------- Configuration ---------------------------

# Reddit API Credentials (Replace with your actual credentials)
REDDIT_CLIENT_ID = ''           # Replace with your Reddit client ID
REDDIT_CLIENT_SECRET = ''       # Replace with your Reddit client secret
REDDIT_USER_AGENT = ''          # Replace with your Reddit user agent

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'  # Update if different

# Maximum number of posts to display on the graph
MAX_POSTS = 100

# ---------------------------------------------------------------------

# --------------------------- Kafka Utilities ---------------------------

def create_kafka_topic(topic_name, num_partitions=1, replication_factor=1):
    """
    Creates a Kafka topic with the specified name, partitions, and replication factor.
    """
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
    """
    Sets up Kafka topics for the specified list of subreddits.
    """
    for subreddit in subreddits:
        topic_name = f"reddit_{subreddit.lower()}"
        create_kafka_topic(topic_name)

# --------------------------- Reddit Streaming ---------------------------

def initialize_praw():
    """
    Initializes and returns a PRAW Reddit instance.
    """
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )
    return reddit

def reddit_stream(reddit, subreddits, keywords, producer, update_content_callback, stop_event):
    """
    Fetches existing comments and streams new comments from Reddit subreddits,
    filters based on keywords, sends relevant comments to Kafka topics,
    and updates the UI with content.
    """
    subreddit_str = '+'.join(subreddits)
    subreddit = reddit.subreddit(subreddit_str)
    compiled_keywords = [re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE) for keyword in keywords] if keywords else []

    # Set to keep track of processed comment IDs to avoid duplicates
    processed_comments = set()

    try:
        # First, fetch existing comments
        for comment in subreddit.comments(limit=None):
            if stop_event.is_set():
                print("Streaming thread received stop signal.")
                break

            body = comment.body
            author = comment.author.name if comment.author else "Unknown"
            subreddit_name = comment.subreddit.display_name
            created_utc = comment.created_utc
            comment_id = comment.id
            permalink = comment.permalink

            # Check if comment is already processed
            if comment_id in processed_comments:
                continue
            processed_comments.add(comment_id)

            # Check if any keyword is in the comment
            is_analyzed = any(keyword.search(body) for keyword in compiled_keywords)

            # Prepare data for UI
            data_for_ui = {
                'subreddit': subreddit_name,
                'author': author,
                'body': body,
                'created_utc': created_utc,
                'id': comment_id,
                'permalink': f"https://www.reddit.com{permalink}",
                'is_analyzed': is_analyzed
            }

            # Update UI with Reddit comment using thread-safe method
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
                producer.send(topic_name, value=data)
                print(f"Sent to Kafka topic '{topic_name}': {comment_id}")

            # Respect Reddit's rate limits
            time.sleep(0.1)  # Reduced sleep time for initial fetching

        # Now, start streaming new comments
        while not stop_event.is_set():
            for comment in subreddit.stream.comments(skip_existing=True, pause_after=1):
                if stop_event.is_set():
                    print("Streaming thread received stop signal.")
                    break

                if comment is None:
                    continue  # No new comment, continue the loop

                body = comment.body
                author = comment.author.name if comment.author else "Unknown"
                subreddit_name = comment.subreddit.display_name
                created_utc = comment.created_utc
                comment_id = comment.id
                permalink = comment.permalink

                # Check if comment is already processed
                if comment_id in processed_comments:
                    continue
                processed_comments.add(comment_id)

                # Check if any keyword is in the comment
                is_analyzed = any(keyword.search(body) for keyword in compiled_keywords)

                # Prepare data for UI
                data_for_ui = {
                    'subreddit': subreddit_name,
                    'author': author,
                    'body': body,
                    'created_utc': created_utc,
                    'id': comment_id,
                    'permalink': f"https://www.reddit.com{permalink}",
                    'is_analyzed': is_analyzed
                }

                # Update UI with Reddit comment using thread-safe method
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
                    producer.send(topic_name, value=data)
                    print(f"Sent to Kafka topic '{topic_name}': {comment_id}")

                # Respect Reddit's rate limits
                time.sleep(1)
    except Exception as e:
        print(f"Error in Reddit stream: {e}")

# --------------------------- Sentiment Analysis Consumer ---------------------------

class SentimentConsumer(threading.Thread):
    def __init__(self, selected_subreddits, keyword, update_callback, stop_event):
        super().__init__()
        self.selected_subreddits = selected_subreddits
        self.keyword = keyword
        self.update_callback = update_callback
        self.consumer = None
        self.stop_event = stop_event

    def run(self):
        """
        Initializes the Kafka consumer and processes incoming messages.
        """
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
                for topic_partition, messages in message_batch.items():
                    for message in messages:
                        data = message.value
                        body = data['body']
                        subreddit_name = data['subreddit']
                        if self.keyword.lower() in body.lower():
                            sentiment = self.perform_sentiment_analysis(body)
                            self.update_callback(subreddit_name, sentiment)
        except Exception as e:
            print(f"Error in SentimentConsumer: {e}")

    def perform_sentiment_analysis(self, text):
        """
        Performs sentiment analysis using VADER and returns the compound polarity score.
        """
        scores = vader_analyzer.polarity_scores(text)
        return scores['compound']

    def stop(self):
        """
        Stops the consumer thread.
        """
        self.stop_event.set()
        if self.consumer:
            self.consumer.close()
        print("Sentiment consumer stopped.")

# --------------------------- User Interface ---------------------------

class SentimentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reddit Sentiment Analysis")
        self.root.geometry("1400x800")

        # Initialize PRAW and Kafka Producer
        self.reddit = initialize_praw()
        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all'  # Ensure data is properly replicated
        )

        # Initialize Streaming and Consumer Threads
        self.stream_thread = None
        self.consumer_thread = None
        self.stream_stop_event = None
        self.consumer_stop_event = None

        # Data for sentiment graph
        self.sentiment_values = {}
        self.post_count = 0
        self.lines = {}
        self.subreddit_colors = {}  # Mapping subreddit to its color

        # Setup UI Components
        self.setup_ui()

    def setup_ui(self):
        """
        Sets up the user interface components.
        """
        # Frame for Inputs
        input_frame = Frame(self.root)
        input_frame.pack(pady=10)

        # Keyword Input
        keyword_label = Label(input_frame, text="Keyword:", font=("Helvetica", 12))
        keyword_label.grid(row=0, column=0, padx=5, pady=5, sticky=E)
        self.keyword_entry = Entry(input_frame, width=30, font=("Helvetica", 12))
        self.keyword_entry.grid(row=0, column=1, padx=5, pady=5)

        # Subreddit Input
        subreddit_label = Label(input_frame, text="Subreddit(s):", font=("Helvetica", 12))
        subreddit_label.grid(row=1, column=0, padx=5, pady=5, sticky=E)
        self.subreddit_entry = Entry(input_frame, width=30, font=("Helvetica", 12))
        self.subreddit_entry.grid(row=1, column=1, padx=5, pady=5)
        subreddit_info = Label(input_frame, text="(Comma-separated)", font=("Helvetica", 8), fg="grey")
        subreddit_info.grid(row=1, column=2, padx=5, pady=5, sticky=W)

        # Start Button
        self.start_button = Button(
            input_frame,
            text="Start Analysis",
            command=self.start_analysis,
            font=("Helvetica", 12),
            bg='#3c4356',
            fg='#a0a9b9',
            activebackground='#141831',
            activeforeground='#a0a9b9'
        )
        self.start_button.grid(row=2, column=1, padx=5, pady=20)

        # Stop Button
        stop_button = Button(
            input_frame,
            text="Stop Analysis",
            command=self.stop_analysis,
            font=("Helvetica", 12),
            bg='#3c4356',
            fg='#a0a9b9',
            activebackground='#141831',
            activeforeground='#a0a9b9'
        )
        stop_button.grid(row=2, column=2, padx=5, pady=20)

        # Message Label
        self.message_label = Label(input_frame, text="", font=("Helvetica", 12), fg="#FFFFFF")  # Changed to white
        self.message_label.grid(row=3, column=0, columnspan=3, padx=5, pady=5)

        # Frame for Displays
        display_frame = Frame(self.root)
        display_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Reddit Content Display with Tabs
        notebook = ttk.Notebook(display_frame)
        notebook.pack(side=LEFT, padx=5, pady=5, fill=BOTH, expand=True)

        # All Comments Tab
        all_comments_frame = Frame(notebook, bg='#0b0f1c')  # Dark background
        notebook.add(all_comments_frame, text='All Comments')
        self.all_comments_text = scrolledtext.ScrolledText(
            all_comments_frame,
            wrap=WORD,
            width=70,
            height=25,
            font=("Helvetica", 10),
            bg='#0b0f1c',
            fg='#FFFFFF',  # Changed to white
            state='disabled'
        )
        self.all_comments_text.pack(fill=BOTH, expand=True)

        # Analyzed Comments Tab
        analyzed_comments_frame = Frame(notebook, bg='#0b0f1c')  # Dark background
        notebook.add(analyzed_comments_frame, text='Analyzed Comments')
        self.analyzed_comments_text = scrolledtext.ScrolledText(
            analyzed_comments_frame,
            wrap=WORD,
            width=70,
            height=25,
            font=("Helvetica", 10),
            bg='#0b0f1c',
            fg='#FFFFFF',  # Changed to white
            state='disabled'
        )
        self.analyzed_comments_text.pack(fill=BOTH, expand=True)

        # Sentiment Analysis Graph
        graph_frame = Frame(display_frame)
        graph_frame.pack(side=RIGHT, padx=5, pady=5, fill=BOTH, expand=True)

        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.fig.patch.set_facecolor('#455378')  # Set figure background color
        self.ax.set_facecolor('#455378')  # Set axes background color
        self.ax.set_ylim(-1, 1)
        self.ax.set_xlim(0, MAX_POSTS)
        self.ax.set_ylabel('Sentiment Polarity', color='white')
        self.ax.set_xlabel('Number of Posts', color='white')
        self.ax.set_title('Live Sentiment Analysis', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['left'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.xaxis.label.set_color('white')

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)
        self.canvas.draw()

    def start_analysis(self):
        """
        Starts the sentiment analysis based on user input.
        """
        keyword = self.keyword_entry.get().strip()
        if not keyword:
            self.message_label['text'] = "Please enter a keyword for analysis."
            self.message_label['fg'] = "#FFFFFF"  # Changed to white
            return

        subreddits_input = self.subreddit_entry.get().strip()
        if not subreddits_input:
            self.message_label['text'] = "Please enter at least one subreddit."
            self.message_label['fg'] = "#FFFFFF"  # Changed to white
            return

        # Parse subreddits (comma-separated)
        selected_subreddits = [sub.strip() for sub in subreddits_input.split(',') if sub.strip()]
        if not selected_subreddits:
            self.message_label['text'] = "Please enter valid subreddit(s)."
            self.message_label['fg'] = "#FFFFFF"  # Changed to white
            return

        # Check if subreddits exist
        invalid_subreddits = []
        for subreddit in selected_subreddits:
            try:
                # Attempt to fetch the subreddit's ID to check if it exists
                self.reddit.subreddit(subreddit).id
            except prawcore.exceptions.Redirect:
                # Subreddit does not exist
                invalid_subreddits.append(subreddit)
            except prawcore.exceptions.NotFound:
                # Subreddit does not exist
                invalid_subreddits.append(subreddit)
            except Exception as e:
                # Handle other exceptions if needed
                print(f"Error checking subreddit '{subreddit}': {e}")
                invalid_subreddits.append(subreddit)

        if invalid_subreddits:
            self.message_label['text'] = f"The following subreddits do not exist: {', '.join(invalid_subreddits)}"
            self.message_label['fg'] = "#FFFFFF"  # Changed to white
            return

        # Convert subreddit names to lowercase for consistency
        selected_subreddits = [sub.lower() for sub in selected_subreddits]

        # Disable Start button
        self.start_button.config(state=DISABLED)

        # Stop existing streaming and consumer threads if running
        if self.stream_thread and self.stream_thread.is_alive():
            self.stop_streaming()

        if self.consumer_thread and self.consumer_thread.is_alive():
            self.stop_consumer()

        # Create Kafka topics for new subreddits
        setup_kafka_topics(selected_subreddits)

        # Clear previous results
        self.all_comments_text.config(state='normal')
        self.all_comments_text.delete(1.0, END)
        self.all_comments_text.config(state='disabled')

        self.analyzed_comments_text.config(state='normal')
        self.analyzed_comments_text.delete(1.0, END)
        self.analyzed_comments_text.config(state='disabled')

        self.sentiment_values.clear()
        self.post_count = 0
        self.lines.clear()
        self.subreddit_colors.clear()  # Clear previous subreddit colors
        self.ax.cla()
        self.fig.patch.set_facecolor('#455378')  # Set figure background color
        self.ax.set_facecolor('#455378')  # Set axes background color
        self.ax.set_ylim(-1, 1)
        self.ax.set_xlim(0, MAX_POSTS)
        self.ax.set_ylabel('Sentiment Polarity', color='white')
        self.ax.set_xlabel('Number of Posts', color='white')
        self.ax.set_title('Live Sentiment Analysis', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['left'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.xaxis.label.set_color('white')

        # Initialize data structures for subreddits
        colors = ['#FF6F61', '#6B5B95', '#88B04B', '#F7CAC9', '#92A8D1', '#955251', '#B565A7']
        for i, subreddit in enumerate(selected_subreddits):
            subreddit_lower = subreddit.lower()
            self.sentiment_values[subreddit_lower] = deque(maxlen=MAX_POSTS)
            color = colors[i % len(colors)]
            line, = self.ax.plot([], [], color=color, label=subreddit_lower)
            self.lines[subreddit_lower] = line
            self.subreddit_colors[subreddit_lower] = color  # Store the color for the subreddit

        # Add legend to the plot without background box
        legend = self.ax.legend(frameon=False)
        for text in legend.get_texts():
            text.set_color("white")
        self.canvas.draw()

        # Initialize stop events
        self.stream_stop_event = threading.Event()
        self.consumer_stop_event = threading.Event()

        # Start a new streaming thread
        self.stream_thread = threading.Thread(
            target=reddit_stream,
            args=(
                self.reddit,
                selected_subreddits,
                [keyword],
                self.producer,
                self.update_reddit_content,
                self.stream_stop_event
            )
        )
        self.stream_thread.daemon = True
        self.stream_thread.start()

        # Start a new consumer thread
        self.consumer_thread = SentimentConsumer(
            selected_subreddits,
            keyword,
            self.update_sentiment_graph,
            self.consumer_stop_event
        )
        self.consumer_thread.daemon = True
        self.consumer_thread.start()

        # Display message in the window
        self.message_label['text'] = f"Analysis started for keyword '{keyword}' in subreddits: {', '.join(selected_subreddits)}"
        self.message_label['fg'] = "#FFFFFF"  # Changed to white

    def stop_analysis(self):
        """
        Stops the ongoing sentiment analysis gracefully.
        """
        # Stop streaming thread
        if self.stream_thread and self.stream_thread.is_alive():
            self.stop_streaming()

        # Stop consumer thread
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.stop_consumer()

        # Update message label
        self.message_label['text'] = "Analysis stopped."
        self.message_label['fg'] = "#FFFFFF"  # Changed to white

        # Enable Start button
        self.start_button.config(state=NORMAL)

    def stop_streaming(self):
        """
        Stops the Reddit streaming thread gracefully.
        """
        if self.stream_stop_event:
            self.stream_stop_event.set()
        if self.stream_thread:
            self.stream_thread.join()
            print("Streaming thread stopped.")

    def stop_consumer(self):
        """
        Stops the sentiment consumer thread gracefully.
        """
        if self.consumer_stop_event:
            self.consumer_stop_event.set()
        if self.consumer_thread:
            self.consumer_thread.stop()
            self.consumer_thread.join()

    def update_reddit_content(self, data):
        """
        Updates the Reddit content display with new comments being analyzed.
        """
        subreddit = data['subreddit'].lower()  # Normalize to lowercase
        # Include subreddit name with the comment
        content = f"[{subreddit}] {data['body']}\n\n"
        # Update the UI in the main thread
        self.root.after(0, self._insert_content_text, content, data['is_analyzed'], subreddit)

    def _insert_content_text(self, content, is_analyzed, subreddit):
        # Normalize subreddit name to lowercase
        subreddit = subreddit.lower()
        # Get the color for the subreddit
        color = self.subreddit_colors.get(subreddit, '#FFFFFF')  # Default to white

        # Define a unique tag for this subreddit
        tag_name = f"subreddit_{subreddit}"

        # If the tag is not already configured, configure it
        if tag_name not in self.all_comments_text.tag_names():
            self.all_comments_text.tag_configure(tag_name, foreground=color)
            self.analyzed_comments_text.tag_configure(tag_name, foreground=color)

        # Check if the user has scrolled to the bottom in All Comments
        at_bottom_all = self.is_scrolled_to_bottom(self.all_comments_text)

        # Insert into "All Comments" tab
        self.all_comments_text.config(state='normal')
        start_index = self.all_comments_text.index(END)
        self.all_comments_text.insert(END, content)
        end_index = self.all_comments_text.index(END)
        self.all_comments_text.tag_add(tag_name, start_index, end_index)
        if at_bottom_all:
            self.all_comments_text.see(END)
        self.all_comments_text.config(state='disabled')

        if is_analyzed:
            # Check if the user has scrolled to the bottom in Analyzed Comments
            at_bottom_analyzed = self.is_scrolled_to_bottom(self.analyzed_comments_text)

            # Insert into "Analyzed Comments" tab
            self.analyzed_comments_text.config(state='normal')
            start_index = self.analyzed_comments_text.index(END)
            self.analyzed_comments_text.insert(END, content)
            end_index = self.analyzed_comments_text.index(END)
            self.analyzed_comments_text.tag_add(tag_name, start_index, end_index)
            if at_bottom_analyzed:
                self.analyzed_comments_text.see(END)
            self.analyzed_comments_text.config(state='disabled')

    def is_scrolled_to_bottom(self, text_widget):
        """
        Checks if the text widget is scrolled to the bottom.
        """
        return float(text_widget.yview()[1]) >= 0.999

    def update_sentiment_graph(self, subreddit_name, polarity):
        """
        Updates the sentiment graph with new data for the given subreddit.
        """
        subreddit_name = subreddit_name.lower()  # Normalize to lowercase
        if subreddit_name not in self.sentiment_values:
            self.sentiment_values[subreddit_name] = deque(maxlen=MAX_POSTS)
            color = self.subreddit_colors.get(subreddit_name, 'white')
            line, = self.ax.plot([], [], color=color, label=subreddit_name)
            self.lines[subreddit_name] = line
            self.ax.legend(frameon=False)
            for text in self.ax.get_legend().get_texts():
                text.set_color("white")
            self.canvas.draw()

        # Append the new sentiment value
        self.sentiment_values[subreddit_name].append(polarity)

        # Apply rolling average for smoothing
        smoothed_values = pd.Series(self.sentiment_values[subreddit_name]).rolling(window=20, min_periods=1).mean()

        # Update the graph with smoothed values
        line = self.lines[subreddit_name]
        line.set_data(range(len(smoothed_values)), smoothed_values)

        # Adjust the graph limits dynamically
        self.ax.set_xlim(0, len(smoothed_values))
        self.ax.set_ylim(-1, 1)

        self.canvas.draw_idle()

    def get_sentiment_label(self, polarity):
        """
        Returns a sentiment label based on polarity score.
        """
        if polarity > 0.1:
            return "Positive"
        elif polarity < -0.1:
            return "Negative"
        else:
            return "Neutral"

    def on_closing(self):
        """
        Handles application closure by stopping threads gracefully.
        """
        self.stop_analysis()
        self.producer.close()
        self.root.destroy()

# --------------------------- Main Execution ---------------------------

def main():
    root = Tk()
    app = SentimentApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
