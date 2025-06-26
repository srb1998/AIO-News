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
        self.BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
        self.UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
        
        # Token Management
        self.DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", 25000))
        self.COST_PER_1K_TOKENS_GEMINI = float(os.getenv("COST_PER_1K_TOKENS_GEMINI", 0.0))
        self.COST_PER_1K_TOKENS_OPENAI = float(os.getenv("COST_PER_1K_TOKENS_OPENAI", 0.00015))
        
        # Brave Search Configuration
        self.BRAVE_ARTICLE_COUNT_WORLD = int(os.getenv("BRAVE_ARTICLE_COUNT_WORLD", 10))
        self.BRAVE_ARTICLE_COUNT_INDIA = int(os.getenv("BRAVE_ARTICLE_COUNT_INDIA", 8))
        self.BRAVE_CACHE_DURATION = int(os.getenv("BRAVE_CACHE_DURATION", 20))  # minutes
        
        # News Priority Settings
        self.WORLD_NEWS_PRIORITY = float(os.getenv("WORLD_NEWS_PRIORITY", 0.7))
        self.INDIA_NEWS_PRIORITY = float(os.getenv("INDIA_NEWS_PRIORITY", 0.3))
        self.BREAKING_NEWS_BOOST = float(os.getenv("BREAKING_NEWS_BOOST", 2.0))
        
        # Scheduling Configuration
        self.BREAKING_NEWS_CHECK_INTERVAL = int(os.getenv("BREAKING_NEWS_CHECK_INTERVAL", 45))  # minutes
        self.FULL_WORKFLOW_TIMES = ["08:00", "14:00", "20:00"]  # 8 AM, 2 PM, 8 PM
        
        # Breaking News
        self.BREAKING_NEWS_KEYWORDS = [
            "breaking", "urgent", "alert", "just in", "developing", "crisis",
            "emergency", "announced", "confirmed", "exclusive", "major", 
            "shocking", "unprecedented", "critical", "immediate"
        ]
        
        # Enhanced Breaking News Time Window (hours)
        self.BREAKING_NEWS_TIME_WINDOW = int(os.getenv("BREAKING_NEWS_TIME_WINDOW", 4))
        
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
                "name": "BBC Technology",
                "url": "http://feeds.bbci.co.uk/news/technology/rss.xml",
                "category": "tech",
                "reliability": 9
            }
        ]

settings = Settings()