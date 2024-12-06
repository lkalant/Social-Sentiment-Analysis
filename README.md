# Reddit Streaming Sentiment Analysis

## Visual Demo:

<iframe width="560" height="315" src="https://www.youtube.com/embed/7RoJrsfjmKI?si=H4wkAA63vBI6e7xL" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

## Overview

Reddit Streaming Sentiment Analysis is a real-time application that streams comments from chosen subreddits, performs sentiment analysis on the incoming text, and stores the results in Kafka topics. Leveraging PRAW (Python Reddit API Wrapper) for data ingestion, Apache Kafka for message streaming, and VADER for sentiment scoring, this setup provides a robust pipeline to monitor and analyze sentiment trends across multiple subreddits based on user-defined keywords.

**Key Features:**

- **Real-time Comment Streaming:** Continuously fetches live comments from specified subreddits.
- **Sentiment Analysis:** Utilizes VADER to generate sentiment polarity scores for each comment.
- **Kafka Integration:** Writes processed comments and their sentiment scores into Kafka topics, one topic per subreddit.
- **Modular Codebase:** Organized into multiple modules for enhanced maintainability and scalability.
- **User-Friendly UI:** Provides a Tkinter-based interface to monitor comments and visualize sentiment trends in real time.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Features](#features)
- [Future Enhancements](#future-enhancements)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Prerequisites

Before setting up the project, ensure you have the following installed on your system:

1. **Python 3.7+**

   - Verify installation:
     ```bash
     python --version
     pip --version
     ```

2. **Apache Kafka and ZooKeeper**

   - **Kafka:** [Download and Quickstart Guide](https://kafka.apache.org/quickstart)
   - **Spark (Optional for Advanced Processing):** [Download Spark](https://spark.apache.org/downloads.html)

3. **Reddit API Credentials**
   - Register an app to obtain `client_id` and `client_secret` by following PRAW’s [Quickstart Guide](https://praw.readthedocs.io/en/stable/getting_started/quick_start.html).

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/your_username/your_repository.git
   cd your_repository

   ```

2. **Install Python Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   **Dependencies include:**

   - `praw` for Reddit API integration
   - `kafka-python` for Kafka interactions
   - `nltk` and `vader_lexicon` for sentiment analysis
   - `matplotlib` and `tkinter` for visualization and UI
   - `pandas` for data manipulation

## Configuration

1. **Set Up Reddit API Credentials**

   Open `config.py` and fill in your Reddit API credentials:

   ```python
   # config.py

   # Reddit API Credentials
   REDDIT_CLIENT_ID = 'your_client_id'
   REDDIT_CLIENT_SECRET = 'your_client_secret'
   REDDIT_USER_AGENT = 'your_user_agent'

   # Kafka Configuration
   KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'  # Update if different

   # Visualization Constants
   MAX_POSTS = 100
   ```

2. **Download NLTK Data**

   The sentiment analysis module requires the VADER lexicon. If not already downloaded, run the following in Python:

   ```python
   import nltk
   nltk.download('vader_lexicon')
   ```

## Usage

1. **Start ZooKeeper and Kafka Services**

   Open two separate terminal windows or tabs.

   - **Start ZooKeeper:**

     ```bash
     bin/zookeeper-server-start.sh config/zookeeper.properties
     ```

   - **Start Kafka Broker:**
     ```bash
     bin/kafka-server-start.sh config/server.properties
     ```

2. **Run the Application**

   In another terminal, navigate to the project directory and execute:

   ```bash
   python main.py
   ```

   **Application Workflow:**

   - **Input:** Enter a keyword and specify one or more subreddits (comma-separated) in the UI.
   - **Streaming:** The application will create Kafka topics for each subreddit (if they don't already exist) and begin streaming comments containing the specified keyword.
   - **Analysis:** Comments are analyzed for sentiment and stored in their respective Kafka topics.
   - **Visualization:** Sentiment trends are visualized in real time on the UI.

## Project Structure

```
reddit_sentiment_analysis/
├── main.py
├── config.py
├── requirements.txt
├── README.md
├── utils/
│   ├── __init__.py
│   ├── kafka_consumer.py
│   ├── kafka_producer.py
│   ├── kafka_setup.py
│   ├── reddit_stream.py
│   ├── sentiment_analysis.py
│   └── visualization.py
└── ui/
    ├── __init__.py
    └── app_ui.py
```

- **main.py:** Entry point of the application.
- **config.py:** Configuration variables and credentials.
- **requirements.txt:** Python dependencies.
- **utils/:** Utility modules handling Kafka interactions, Reddit streaming, sentiment analysis, and visualization.
- **ui/:** Tkinter-based user interface components.

## Features

- **Real-time Comment Streaming:** Fetches live comments from specified subreddits.
- **Sentiment Analysis:** Uses VADER to score comments for sentiment polarity.
- **Kafka Integration:** Publishes analyzed comments to Kafka topics for each subreddit.
- **User Interface:** Provides a GUI to monitor comments and view sentiment trends.
- **Modular Design:** Organized codebase for scalability and maintainability.

## Future Enhancements

- **Multiple Keywords:** Accept multiple keywords/topics.
- **Word Count:** Use Spacyy for word count via PySpark to keep a running count of named entities.
- **Advanced Analytics:** Integrate Apache Spark for more sophisticated data processing and analysis.
- **Interactive Dashboards:** Develop web-based dashboards for enhanced visualization and interaction.
- **Multi-language Support:** Expand sentiment analysis to support multiple languages.
- **Alerting Mechanisms:** Implement notifications based on sentiment thresholds or significant changes.
- **Dockerization:** Containerize the application for easier deployment and scalability.

## Troubleshooting

- **No Comments Displayed:**

  - Ensure that the selected subreddits are active and that your keyword is present in recent comments.
  - Verify that Kafka and ZooKeeper services are running without errors.

- **Authentication Errors:**

  - Double-check your Reddit API credentials in `config.py`.
  - Ensure that the `user_agent` is descriptive and unique.

- **Kafka Connectivity Issues:**

  - Confirm that the `KAFKA_BOOTSTRAP_SERVERS` address in `config.py` matches your Kafka broker's address.
  - Check if the Kafka broker is running and accessible.

- **Missing Dependencies:**
  - Ensure all dependencies are installed by running `pip install -r requirements.txt`.
  - If issues persist, consider creating a virtual environment.

## License

This project is licensed under the [MIT License](LICENSE).
