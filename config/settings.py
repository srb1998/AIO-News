import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Settings:
    # API Keys
    def __init__(self):
        # API Keys
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.NEWS_API_KEY = os.getenv("NEWS_API_KEY")
        self.UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
        
        # Token Management
        self.DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", 10000))
        self.COST_PER_1K_TOKENS_GEMINI = float(os.getenv("COST_PER_1K_TOKENS_GEMINI", 0.0))
        self.COST_PER_1K_TOKENS_OPENAI = float(os.getenv("COST_PER_1K_TOKENS_OPENAI", 0.00015))
        
        # Breaking News
        self.BREAKING_NEWS_KEYWORDS = os.getenv("BREAKING_NEWS_KEYWORDS", "breaking,urgent,alert").split(",")
        
        # News Sources (RSS Feeds - FREE!)
        self.RSS_SOURCES = [
            {
                "name": "BBC World News",
                "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
                "category": "international",
                "reliability": 9
            },
            {
                "name": "Times of India",
                "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
                "category": "general", 
                "reliability": 9
            },
            {
                "name": "TechCrunch",
                "url": "http://feeds.feedburner.com/TechCrunch/",
                "category": "tech",
                "reliability": 8
            },
            {
                "name": "BBC Technology",
                "url": "http://feeds.bbci.co.uk/news/technology/rss.xml",
                "category": "tech",
                "reliability": 9
            }
        ]

settings = Settings()