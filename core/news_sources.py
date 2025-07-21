import feedparser
import requests
from typing import List, Dict, Any
from datetime import datetime, timedelta
import re
# from bs4 import BeautifulSoup
from config.settings import settings
from core.brave_client import brave_client
import time

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
            for entry in feed.entries[:3]:  # Limit to 8 articles per source

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
                    "is_breaking": self._is_breaking_news(entry.title + " " + getattr(entry, 'description', '')),
                    "source_type": "rss",
                    "priority_boost": 1.0  # Default priority for RSS
                }
                articles.append(article)
            
            print(f"✅ Got {len(articles)} articles from {source['name']}")
            return articles
            
        except Exception as e:
            print(f"❌ Error fetching {source['name']}: {e}")
            return []
    
    def fetch_all_sources(self) -> List[Dict]:
        """Fetch articles from ALL sources (RSS + Brave API)"""
        print("🌐 Fetching from ALL sources (RSS + Brave API)...")
        all_articles = []
        
        # 1. Fetch from RSS sources
        print("\n📡 Phase 1: RSS Sources")
        for source in self.sources:
            articles = self.fetch_rss_feed(source)
            all_articles.extend(articles)
        
        # 2. Fetch from Brave API
        print("\n🔍 Phase 2: Brave Search API")
        try:
            # Get World News
            world_articles = brave_client.get_world_news()
            all_articles.extend(world_articles)
            time.sleep(1)  # Avoid hitting rate limits
            # Get India News
            india_articles = brave_client.get_india_news()
            all_articles.extend(india_articles)
            
        except Exception as e:
            print(f"⚠️ Brave API fetch failed: {e}")
        
        # 3. Process and deduplicate
        print(f"\n🔄 Processing {len(all_articles)} total articles...")
        
        # Remove duplicates
        unique_articles = self._deduplicate_articles(all_articles)
        print(f"📝 After deduplication: {len(unique_articles)} unique articles")
        
        # Sort by priority and freshness
        sorted_articles = self._sort_articles_by_priority(unique_articles)
        
        print(f"✅ Final result: {len(sorted_articles)} articles ready for processing")
        return sorted_articles
    
    def get_breaking_news(self) -> List[Dict]:
        """Get ONLY breaking news from all sources"""
        print("🚨 Collecting breaking news from all sources...")
        breaking_articles = []
        
        # 1. RSS Breaking News
        rss_articles = []
        for source in self.sources:
            articles = self.fetch_rss_feed(source)
            rss_articles.extend(articles)
        
        rss_breaking = [article for article in rss_articles if article['is_breaking']]
        breaking_articles.extend(rss_breaking)
        
        # 2. Brave API Breaking News
        try:
            brave_breaking = brave_client.get_breaking_news()
            breaking_articles.extend(brave_breaking)
        except Exception as e:
            print(f"⚠️ Brave breaking news fetch failed: {e}")
        
        # 3. Filter for very recent breaking news (last 4 hours)
        recent_breaking = self._filter_very_recent(breaking_articles, hours=4)
        
        # 4. Deduplicate and sort
        unique_breaking = self._deduplicate_articles(recent_breaking)
        sorted_breaking = sorted(unique_breaking, key=lambda x: x['published'], reverse=True)
        
        print(f"🚨 Found {len(sorted_breaking)} unique breaking news articles")
        return sorted_breaking[:10]  # Top 10 breaking news
    
    def _deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on title similarity"""
        unique_articles = []
        seen_titles = set()
        
        for article in articles:
            title_clean = self._clean_title_for_comparison(article['title'])
            
            # Check for similarity with existing titles
            is_duplicate = False
            for seen_title in seen_titles:
                if self._titles_are_similar(title_clean, seen_title):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_articles.append(article)
                seen_titles.add(title_clean)
        
        return unique_articles
    
    def _clean_title_for_comparison(self, title: str) -> str:
        """Clean title for better comparison"""
        # Remove common prefixes/suffixes
        title = re.sub(r'^(BREAKING|URGENT|LIVE|UPDATE):\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*-\s*(BBC|CNN|Reuters|TOI).*$', '', title, flags=re.IGNORECASE)
        return title.lower().strip()
    
    def _titles_are_similar(self, title1: str, title2: str, threshold: float = 0.75) -> bool:
        """Check if two titles are similar using word overlap"""
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        if not words1 or not words2:
            return False
        
        overlap = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        similarity = overlap / union if union > 0 else 0
        return similarity >= threshold
    
    def _sort_articles_by_priority(self, articles: List[Dict]) -> List[Dict]:
        """Sort articles by priority score"""
        def calculate_priority_score(article):
            base_score = article.get('reliability', 5)
            
            # Apply priority boost
            priority_boost = article.get('priority_boost', 1.0)
            base_score *= priority_boost
            
            # Breaking news boost
            if article.get('is_breaking', False):
                base_score *= settings.BREAKING_NEWS_BOOST
            
            # Freshness bonus (more recent = higher score)
            hours_old = (datetime.now() - article['published']).total_seconds() / 3600
            freshness_bonus = max(0, 10 - hours_old)  # Bonus decreases with age
            base_score += freshness_bonus
            
            # Source type bonus (Brave API might have more variety)
            if article.get('source_type') == 'brave_api':
                base_score += 1
            
            return base_score
        
        return sorted(articles, key=calculate_priority_score, reverse=True)
    
    def _filter_very_recent(self, articles: List[Dict], hours: int = 4) -> List[Dict]:
        """Filter for very recent articles (for breaking news)"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [article for article in articles if article['published'] >= cutoff_time]
    
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
        # if hasattr(entry, 'description'):
        #     soup = BeautifulSoup(entry.description, 'html.parser')
        #     img_tag = soup.find('img')
        #     if img_tag and img_tag.get('src'):
        #         return img_tag['src']
        
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
    
    def get_source_summary(self) -> Dict[str, Any]:
        """Get summary of all news sources"""
        return {
            "rss_sources": len(self.sources),
            "rss_source_names": [source['name'] for source in self.sources],
            "brave_api_enabled": bool(settings.BRAVE_API_KEY),
            "world_news_count": settings.BRAVE_ARTICLE_COUNT_WORLD,
            "india_news_count": settings.BRAVE_ARTICLE_COUNT_INDIA,
            "total_expected_articles": len(self.sources) * 8 + settings.BRAVE_ARTICLE_COUNT_WORLD + settings.BRAVE_ARTICLE_COUNT_INDIA
        }