import feedparser
import requests
from typing import List, Dict, Any
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
from config.settings import settings

class NewsSourceManager:
    def __init__(self):
        self.sources = settings.RSS_SOURCES
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AI-News-Agency/1.0 (Educational Purpose)'
        })
    
    def fetch_rss_feed(self, source: Dict) -> List[Dict]:
        """Fetch articles from RSS feed"""
        try:
            print(f"📡 Fetching from {source['name']}...")
            feed = feedparser.parse(source['url'])
            
            articles = []
            for entry in feed.entries[:8]:  # Limit to 10 articles per source

                # Extract image URL
                image_url = self._extract_image_from_entry(entry)
                
                # Check if it's recent (last 24 hours)
                pub_date = self._parse_date(entry)
                if pub_date and (datetime.now() - pub_date).days > 1:
                    continue
                
                article = {
                    "title": entry.title,
                    "description": getattr(entry, 'description', ''),
                    "url": entry.link,
                    "published": pub_date,
                    "source": source['name'],
                    "category": source['category'],
                    "reliability": source['reliability'],
                    "image_url": image_url,
                    "is_breaking": self._is_breaking_news(entry.title + " " + getattr(entry, 'description', ''))
                }
                articles.append(article)
            
            print(f"✅ Got {len(articles)} articles from {source['name']}")
            return articles
            
        except Exception as e:
            print(f"❌ Error fetching {source['name']}: {e}")
            return []
    
    def _extract_image_from_entry(self, entry) -> str:
        """Extract image URL from RSS entry"""
        # Try different RSS image fields
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image'):
                    return media.get('url', '')
        
        if hasattr(entry, 'media_thumbnail'):
            return entry.media_thumbnail[0].get('url', '') if entry.media_thumbnail else ''
        
        # Try to extract from description HTML
        if hasattr(entry, 'description'):
            soup = BeautifulSoup(entry.description, 'html.parser')
            img_tag = soup.find('img')
            if img_tag and img_tag.get('src'):
                return img_tag['src']
        
        return ""
    
    def _parse_date(self, entry) -> datetime:
        """Parse publication date from RSS entry"""
        try:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                return datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6])
        except:
            pass
        return datetime.now()
    
    def _is_breaking_news(self, text: str) -> bool:
        """Check if article contains breaking news keywords"""
        text_lower = text.lower()
        return any(keyword.strip().lower() in text_lower for keyword in settings.BREAKING_NEWS_KEYWORDS)
    
    def fetch_all_sources(self) -> List[Dict]:
        """Fetch articles from all configured sources"""
        all_articles = []
        
        for source in self.sources:
            articles = self.fetch_rss_feed(source)
            all_articles.extend(articles)
        
        # Sort by reliability and recency
        all_articles.sort(key=lambda x: (x['reliability'], x['published']), reverse=True)
        
        return all_articles
    
    def get_breaking_news(self) -> List[Dict]:
        """Get only breaking news articles"""
        all_articles = self.fetch_all_sources()
        breaking_news = [article for article in all_articles if article['is_breaking']]
        
        # Sort by recency for breaking news
        breaking_news.sort(key=lambda x: x['published'], reverse=True)
        
        return breaking_news[:5]  # Top 5 breaking news