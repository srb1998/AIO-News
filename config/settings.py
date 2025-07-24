# FILE: config/settings.py (Updated with minor fixes and Phase 2 preparation)

import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Settings:
    def __init__(self):
        # Create output directory if it doesn't exist
        os.makedirs("data/outputs/workflow", exist_ok=True)  # Ensure output directory exists
        
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
        self.BRAVE_ARTICLE_COUNT_WORLD = int(os.getenv("BRAVE_ARTICLE_COUNT_WORLD", 3))
        self.BRAVE_ARTICLE_COUNT_INDIA = int(os.getenv("BRAVE_ARTICLE_COUNT_INDIA", 5))
        self.BRAVE_CACHE_DURATION = int(os.getenv("BRAVE_CACHE_DURATION", 20))  # minutes
        
        # News Priority Settings
        self.WORLD_NEWS_PRIORITY = float(os.getenv("WORLD_NEWS_PRIORITY", 0.2))
        self.INDIA_NEWS_PRIORITY = float(os.getenv("INDIA_NEWS_PRIORITY", 0.8))
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

        # Service Configuration
        self.SERVICE_CONFIG = {
            "workflow_interval_hours": 6,
            "max_workflow_history": 24,
            "service_heartbeat_seconds": 60,
            "auto_save_results": True,
            "results_directory": "data/outputs",
            "service_log_level": "INFO",
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
        }

        # Workflow Timing
        self.WORKFLOW_TIMING = {
            "daily_workflow_interval": 3 * 60 * 60,  # 3 hours in seconds
            "breaking_news_check_interval": 30 * 60,  # 30 minutes for breaking news
            "service_status_check_interval": 5 * 60,  # 5 minutes for status updates
            "posting_scheduler_interval_seconds": 2 * 60, # Check for approved posts every 2 minutes
            "min_posting_delay_seconds": 10 * 60, # Minimum 10 minutes between posts
            "max_posting_delay_seconds": 25 * 60
        }

        # Telegram Configuration (for Phase 2)
        self.TELEGRAM_CONFIG = {
            "polling_interval_seconds": 2,
            "approval_timeout_minutes": 30,
            "approval_storage_path": "data/approvals/",
            "images_storage_path": "data/outputs/images/",
            "videos_storage_path": "data/outputs/videos/",
            "max_retries": 5,
            "retry_delay_seconds": 5
        }
        self.WEB_UPLOADER_BASE_URL = "https://media-web-uploader.vercel.app/" # The URL of your index.html

        # Create approval storage directory for Phase 2
        os.makedirs(self.TELEGRAM_CONFIG["approval_storage_path"], exist_ok=True)
        os.makedirs(self.TELEGRAM_CONFIG["images_storage_path"], exist_ok=True)
        os.makedirs(self.TELEGRAM_CONFIG["videos_storage_path"], exist_ok=True)

settings = Settings()