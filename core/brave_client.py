import requests
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from config.settings import settings

class BraveNewsClient:
    def __init__(self):
        self.api_key = settings.BRAVE_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/news/search"
        self.session = requests.Session()
        self.session.headers.update({
            'X-Subscription-Token': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'AI-News-Agency/1.0',
            "Accept-Encoding": "gzip"
        })
        
        # Simple cache to avoid duplicate API calls
        self._cache = {}
        self._cache_timestamps = {}
    
    def search_news(self, query: str, count: int = 10, region: str = "ALL") -> List[Dict[str, Any]]:
        """
        Search news using Brave Search API
        
        Args:
            query: Search query (e.g., "Top World News", "India Top News")
            count: Number of articles to fetch
            region: Region filter (default: "ALL")
        
        Returns:
            List of formatted news articles
        """
        
        # Check cache first
        cache_key = f"{query}_{count}_{region}"
        if self._is_cache_valid(cache_key):
            print(f"📋 Using cached results for: {query}")
            return self._cache[cache_key]
        
        try:
            print(f"🔍 Searching Brave API: {query} ({count} articles)")
            
            params = {
                'q': query,
                'count': count,
                'search_lang': 'en',
                'safesearch': 'off',
                'freshness': 'pd',  # Past day (24 hours)
                'text_decorations': False,
                'spellcheck': True
            }
            if region != "ALL":
                params['country'] = region
            print("🔗 Brave API Params:", params)
            response = self.session.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = self._format_brave_articles(data.get('results', []), query)
            for article in articles:
                if article["url"].endswith(".com") or "/news" not in article["url"]:
                    continue
            # Cache the results
            self._cache[cache_key] = articles
            self._cache_timestamps[cache_key] = time.time()
            
            print(f"✅ Brave API: Found {len(articles)} articles for '{query}'")
            return articles
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Brave API error for '{query}': {e}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error in Brave search: {e}")
            return []
    
    def get_world_news(self) -> List[Dict[str, Any]]:
        """Get top world news"""
        return self.search_news(
            query="Top World News",
            count=settings.BRAVE_ARTICLE_COUNT_WORLD,
            region="ALL"
        )
    
    def get_india_news(self) -> List[Dict[str, Any]]:
        """Get top India news"""
        today = datetime.now().strftime("%B %d %Y")
        return self.search_news(
            query=f"Top India news {today}",
            count=settings.BRAVE_ARTICLE_COUNT_INDIA,
            region="IN"
        )
    
    def get_breaking_news(self) -> List[Dict[str, Any]]:
        """Get breaking news specifically"""
        breaking_queries = [
            "breaking news today urgent",
            "developing story live updates",
            "just announced major news"
        ]
        
        all_breaking = []
        for query in breaking_queries:
            articles = self.search_news(query, count=5, region="ALL")
            # Only include very recent articles (last 4 hours for breaking)
            recent_articles = self._filter_recent_articles(articles, hours=4)
            all_breaking.extend(recent_articles)
        
        # Remove duplicates and sort by freshness
        unique_articles = self._deduplicate_articles(all_breaking)
        return sorted(unique_articles, key=lambda x: x['published'], reverse=True)[:8]
    
    def _format_brave_articles(self, brave_results: List[Dict], query: str) -> List[Dict[str, Any]]:
        """Format Brave API results to match our article structure"""
        articles = []
        
        for result in brave_results:
            try:
                # Parse age to get published date
                published_date = self._parse_brave_age(result.get('age', ''))
                
                article = {
                    "title": result.get('title', ''),
                    "description": result.get('description', ''),
                    "url": result.get('url', ''),
                    "published": published_date,
                    "source": self._extract_source_name(result.get('url', '')),
                    "category": self._categorize_by_query(query),
                    "reliability": self._estimate_source_reliability(result.get('url', '')),
                    "image_url": result.get('thumbnail', {}).get('src', '') if result.get('thumbnail') else '',
                    "is_breaking": self._is_breaking_news_brave(result.get('title', '') + " " + result.get('description', '')),
                    "source_type": "brave_api",
                    "priority_boost": settings.WORLD_NEWS_PRIORITY if "world" in query.lower() else settings.INDIA_NEWS_PRIORITY
                }
                
                # Apply breaking news boost
                if article['is_breaking']:
                    article['priority_boost'] *= settings.BREAKING_NEWS_BOOST
                
                articles.append(article)
                
            except Exception as e:
                print(f"⚠️ Error formatting Brave article: {e}")
                continue
        
        return articles
    
    def _parse_brave_age(self, age_str: str) -> datetime:
        """Parse Brave's age string to datetime"""
        try:
            now = datetime.now()
            age_str = age_str.lower()
            
            if 'hour' in age_str:
                hours = int(''.join(filter(str.isdigit, age_str.split('hour')[0])))
                return now - timedelta(hours=hours)
            elif 'minute' in age_str:
                minutes = int(''.join(filter(str.isdigit, age_str.split('minute')[0])))
                return now - timedelta(minutes=minutes)
            elif 'day' in age_str:
                days = int(''.join(filter(str.isdigit, age_str.split('day')[0])))
                return now - timedelta(days=days)
            else:
                return now - timedelta(hours=1)  # Default to 1 hour ago
                
        except:
            return datetime.now() - timedelta(hours=2)  # Default fallback
    
    def _extract_source_name(self, url: str) -> str:
        """Extract source name from URL"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return domain.replace('www.', '').split('.')[0].title()
        except:
            return "Unknown Source"
    
    def _categorize_by_query(self, query: str) -> str:
        """Categorize article based on search query"""
        query_lower = query.lower()
        if 'india' in query_lower:
            return 'india'
        elif 'world' in query_lower or 'international' in query_lower:
            return 'international'
        elif 'tech' in query_lower:
            return 'tech'
        elif 'business' in query_lower:
            return 'business'
        else:
            return 'general'
    
    def _estimate_source_reliability(self, url: str) -> int:
        """Estimate source reliability based on domain"""
        reliable_sources = {
            'bbc.com': 9, 'reuters.com': 9, 'apnews.com': 9,
            'cnn.com': 8, 'theguardian.com': 8, 'nytimes.com': 9,
            'timesofindia.com': 8, 'hindustantimes.com': 7,
            'ndtv.com': 7, 'thehindu.com': 8, 'indianexpress.com': 8
        }
        
        for domain, score in reliable_sources.items():
            if domain in url:
                return score
        
        return 6  # Default reliability score
    
    def _is_breaking_news_brave(self, text: str) -> bool:
        """Check if article is breaking news"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in settings.BREAKING_NEWS_KEYWORDS)
    
    def _filter_recent_articles(self, articles: List[Dict], hours: int = 24) -> List[Dict]:
        """Filter articles to only include recent ones"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [article for article in articles if article['published'] >= cutoff_time]
    
    def _deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on title similarity"""
        unique_articles = []
        seen_titles = set()
        
        for article in articles:
            title_words = set(article['title'].lower().split())
            is_duplicate = False
            
            for seen_title in seen_titles:
                seen_words = set(seen_title.split())
                # If 70% of words match, consider it duplicate
                if len(title_words.intersection(seen_words)) / len(title_words.union(seen_words)) > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_articles.append(article)
                seen_titles.add(article['title'].lower())
        
        return unique_articles
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self._cache_timestamps:
            return False
        
        cache_age_minutes = (time.time() - self._cache_timestamps[cache_key]) / 60
        return cache_age_minutes < settings.BRAVE_CACHE_DURATION
    
    def clear_cache(self):
        """Clear the cache manually"""
        self._cache.clear()
        self._cache_timestamps.clear()
        print("🧹 Brave API cache cleared")

# Global Brave client
brave_client = BraveNewsClient()