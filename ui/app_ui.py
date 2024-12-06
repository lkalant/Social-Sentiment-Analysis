# ui/app_ui.py

from tkinter import *
from tkinter import ttk, scrolledtext
from collections import deque
from config import MAX_POSTS
from utils.kafka_setup import setup_kafka_topics
from utils.kafka_consumer import SentimentConsumer
from utils.kafka_producer import KafkaProducerHandler
from utils.reddit_stream import reddit_stream
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, KAFKA_BOOTSTRAP_SERVERS, MAX_POSTS
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import praw
import prawcore
import threading
import json
import time

matplotlib.use('TkAgg')

class SentimentAppUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Reddit Sentiment Analysis")
        self.root.geometry("1400x800")

        # Initialize Reddit and Kafka Producer
        self.reddit = self.initialize_praw()
        self.kafka_producer_handler = KafkaProducerHandler()

        self.stream_thread = None
        self.consumer_thread = None
        self.stream_stop_event = None
        self.consumer_stop_event = None

        self.sentiment_values = {}
        self.post_count = 0
        self.lines = {}
        self.subreddit_colors = {}

        self.setup_ui()

    def initialize_praw(self):
        return praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )

    def setup_ui(self):
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

        self.message_label = Label(input_frame, text="", font=("Helvetica", 12), fg="#FFFFFF")
        self.message_label.grid(row=3, column=0, columnspan=3, padx=5, pady=5)

        display_frame = Frame(self.root)
        display_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        notebook = ttk.Notebook(display_frame)
        notebook.pack(side=LEFT, padx=5, pady=5, fill=BOTH, expand=True)

        all_comments_frame = Frame(notebook, bg='#0b0f1c')
        notebook.add(all_comments_frame, text='All Comments')
        self.all_comments_text = scrolledtext.ScrolledText(
            all_comments_frame,
            wrap=WORD,
            width=70,
            height=25,
            font=("Helvetica", 10),
            bg='#0b0f1c',
            fg='#FFFFFF',
            state='disabled'
        )
        self.all_comments_text.pack(fill=BOTH, expand=True)

        analyzed_comments_frame = Frame(notebook, bg='#0b0f1c')
        notebook.add(analyzed_comments_frame, text='Analyzed Comments')
        self.analyzed_comments_text = scrolledtext.ScrolledText(
            analyzed_comments_frame,
            wrap=WORD,
            width=70,
            height=25,
            font=("Helvetica", 10),
            bg='#0b0f1c',
            fg='#FFFFFF',
            state='disabled'
        )
        self.analyzed_comments_text.pack(fill=BOTH, expand=True)

        graph_frame = Frame(display_frame)
        graph_frame.pack(side=RIGHT, padx=5, pady=5, fill=BOTH, expand=True)

        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.fig.patch.set_facecolor('#455378')
        self.ax.set_facecolor('#455378')
        self.ax.set_ylim(-1, 1)
        self.ax.set_xlim(0, MAX_POSTS)
        self.ax.set_ylabel('Sentiment Polarity', color='white')
        self.ax.set_xlabel('Number of Posts', color='white')
        self.ax.set_title('Live Sentiment Analysis', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.xaxis.label.set_color('white')

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)
        self.canvas.draw()

    def start_analysis(self):
        keyword = self.keyword_entry.get().strip()
        if not keyword:
            self.display_message("Please enter a keyword for analysis.", "white")
            return

        subreddits_input = self.subreddit_entry.get().strip()
        if not subreddits_input:
            self.display_message("Please enter at least one subreddit.", "white")
            return

        selected_subreddits = [sub.strip() for sub in subreddits_input.split(',') if sub.strip()]
        if not selected_subreddits:
            self.display_message("Please enter valid subreddit(s).", "white")
            return

        # Check if subreddits exist
        invalid_subreddits = []
        for subreddit in selected_subreddits:
            try:
                self.reddit.subreddit(subreddit).id
            except prawcore.exceptions.Redirect:
                invalid_subreddits.append(subreddit)
            except prawcore.exceptions.NotFound:
                invalid_subreddits.append(subreddit)
            except Exception as e:
                print(f"Error checking subreddit '{subreddit}': {e}")
                invalid_subreddits.append(subreddit)

        if invalid_subreddits:
            self.display_message(f"The following subreddits do not exist: {', '.join(invalid_subreddits)}", "white")
            return

        selected_subreddits = [sub.lower() for sub in selected_subreddits]

        self.start_button.config(state=DISABLED)

        if self.stream_thread and self.stream_thread.is_alive():
            self.stop_streaming()

        if self.consumer_thread and self.consumer_thread.is_alive():
            self.stop_consumer()

        # Setup Kafka topics
        setup_kafka_topics(selected_subreddits)

        # Clear previous data
        self.all_comments_text.config(state='normal')
        self.all_comments_text.delete(1.0, END)
        self.all_comments_text.config(state='disabled')

        self.analyzed_comments_text.config(state='normal')
        self.analyzed_comments_text.delete(1.0, END)
        self.analyzed_comments_text.config(state='disabled')

        self.sentiment_values.clear()
        self.post_count = 0
        self.lines.clear()
        self.subreddit_colors.clear()
        self.ax.cla()
        self.fig.patch.set_facecolor('#455378')
        self.ax.set_facecolor('#455378')
        self.ax.set_ylim(-1, 1)
        self.ax.set_xlim(0, MAX_POSTS)
        self.ax.set_ylabel('Sentiment Polarity', color='white')
        self.ax.set_xlabel('Number of Posts', color='white')
        self.ax.set_title('Live Sentiment Analysis', color='white')
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.ax.yaxis.label.set_color('white')
        self.ax.xaxis.label.set_color('white')

        # Assign colors to subreddits
        colors = ['#FF6F61', '#6B5B95', '#88B04B', '#F7CAC9', '#92A8D1', '#955251', '#B565A7']
        for i, subreddit in enumerate(selected_subreddits):
            self.sentiment_values[subreddit] = deque(maxlen=MAX_POSTS)
            color = colors[i % len(colors)]
            line, = self.ax.plot([], [], color=color, label=subreddit)
            self.lines[subreddit] = line
            self.subreddit_colors[subreddit] = color

        legend = self.ax.legend(frameon=False)
        for text in legend.get_texts():
            text.set_color("white")
        self.canvas.draw()

        self.stream_stop_event = threading.Event()
        self.consumer_stop_event = threading.Event()

        # Start streaming thread
        self.stream_thread = threading.Thread(
            target=reddit_stream,
            args=(
                self.reddit,
                selected_subreddits,
                [keyword],
                self.kafka_producer_handler,
                self.update_reddit_content,
                self.stream_stop_event
            ),
            daemon=True
        )
        self.stream_thread.start()

        # Start consumer thread
        self.consumer_thread = SentimentConsumer(
            selected_subreddits,
            keyword,
            self.update_sentiment_graph,
            self.consumer_stop_event
        )
        self.consumer_thread.daemon = True
        self.consumer_thread.start()

        self.display_message(f"Analysis started for keyword '{keyword}' in subreddits: {', '.join(selected_subreddits)}", "white")

    def stop_analysis(self):
        if self.stream_thread and self.stream_thread.is_alive():
            self.stop_streaming()

        if self.consumer_thread and self.consumer_thread.is_alive():
            self.stop_consumer()

        self.display_message("Analysis stopped.", "white")
        self.start_button.config(state=NORMAL)

    def stop_streaming(self):
        if self.stream_stop_event:
            self.stream_stop_event.set()
        if self.stream_thread:
            self.stream_thread.join()
            print("Streaming thread stopped.")

    def stop_consumer(self):
        if self.consumer_stop_event:
            self.consumer_stop_event.set()
        if self.consumer_thread:
            self.consumer_thread.stop()
            self.consumer_thread.join()

    def update_reddit_content(self, data):
        subreddit = data['subreddit'].lower()
        content = f"[{subreddit}] {data['body']}\n\n"
        self.root.after(0, self._insert_content_text, content, data['is_analyzed'], subreddit)

    def _insert_content_text(self, content, is_analyzed, subreddit):
        subreddit = subreddit.lower()
        color = self.subreddit_colors.get(subreddit, '#FFFFFF')

        tag_name = f"subreddit_{subreddit}"
        if tag_name not in self.all_comments_text.tag_names():
            self.all_comments_text.tag_configure(tag_name, foreground=color)
            self.analyzed_comments_text.tag_configure(tag_name, foreground=color)

        at_bottom_all = self.is_scrolled_to_bottom(self.all_comments_text)
        self.all_comments_text.config(state='normal')
        start_index = self.all_comments_text.index(END)
        self.all_comments_text.insert(END, content)
        end_index = self.all_comments_text.index(END)
        self.all_comments_text.tag_add(tag_name, start_index, end_index)
        if at_bottom_all:
            self.all_comments_text.see(END)
        self.all_comments_text.config(state='disabled')

        if is_analyzed:
            at_bottom_analyzed = self.is_scrolled_to_bottom(self.analyzed_comments_text)
            self.analyzed_comments_text.config(state='normal')
            start_index = self.analyzed_comments_text.index(END)
            self.analyzed_comments_text.insert(END, content)
            end_index = self.analyzed_comments_text.index(END)
            self.analyzed_comments_text.tag_add(tag_name, start_index, end_index)
            if at_bottom_analyzed:
                self.analyzed_comments_text.see(END)
            self.analyzed_comments_text.config(state='disabled')

    def is_scrolled_to_bottom(self, text_widget):
        return float(text_widget.yview()[1]) >= 0.999

    def update_sentiment_graph(self, subreddit_name, polarity):
        subreddit_name = subreddit_name.lower()
        if subreddit_name not in self.sentiment_values:
            self.sentiment_values[subreddit_name] = deque(maxlen=MAX_POSTS)
            color = self.subreddit_colors.get(subreddit_name, 'white')
            line, = self.ax.plot([], [], color=color, label=subreddit_name)
            self.lines[subreddit_name] = line
            self.ax.legend(frameon=False)
            for text in self.ax.get_legend().get_texts():
                text.set_color("white")
            self.canvas.draw()

        self.sentiment_values[subreddit_name].append(polarity)
        smoothed_values = pd.Series(self.sentiment_values[subreddit_name]).rolling(window=20, min_periods=1).mean()

        line = self.lines[subreddit_name]
        line.set_data(range(len(smoothed_values)), smoothed_values)

        self.ax.set_xlim(0, len(smoothed_values))
        self.ax.set_ylim(-1, 1)
        self.canvas.draw_idle()

    def display_message(self, message, color):
        self.message_label.config(text=message, fg=color)

    def on_closing(self):
        self.stop_analysis()
        self.kafka_producer_handler.close()
        self.root.destroy()
