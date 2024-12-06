# utils/sentiment_analysis.py

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Ensure the lexicon is downloaded
nltk.download('vader_lexicon', quiet=True)

vader_analyzer = SentimentIntensityAnalyzer()

def analyze_sentiment(text):
    scores = vader_analyzer.polarity_scores(text)
    return scores['compound']
