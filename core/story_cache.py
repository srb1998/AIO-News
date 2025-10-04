# story_cache.py

import json
import os
import re
from typing import Set
from datetime import datetime, timedelta

class StoryCache:
    """
    File-based cache with better duplicate detection and automatic pruning,
    """
    def __init__(self, cache_file='data/story_cache.json', max_age_seconds=86400): # 24 hours
        self.cache_file = cache_file
        self.max_age = timedelta(seconds=max_age_seconds)
        self._ensure_cache_exists()

    def _ensure_cache_exists(self):
        """Creates cache file and directory if missing"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, 'w') as f:
                json.dump({}, f)

    def _load_cache(self) -> dict:
        """
        Loads cache and converts ISO string timestamps back to datetime objects.
        """
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

                for key, value in cache_data.items():
                    if 'timestamp' in value and isinstance(value['timestamp'], str):
                        try:
                            value['timestamp'] = datetime.fromisoformat(value['timestamp'])
                        except (ValueError, TypeError):
                            
                            value['timestamp'] = datetime.fromtimestamp(float(value['timestamp']))
                return cache_data
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_cache(self, cache_data: dict):
        """
        Saves cache data to file, converting datetime objects to ISO strings.
        """
        serializable_cache = {}

        for key, value in cache_data.items():
            serializable_cache[key] = value.copy()
            if 'timestamp' in serializable_cache[key] and isinstance(serializable_cache[key]['timestamp'], datetime):
                serializable_cache[key]['timestamp'] = serializable_cache[key]['timestamp'].isoformat()
        
        with open(self.cache_file, 'w') as f:
            json.dump(serializable_cache, f, indent=2)

    def _normalize_headline(self, headline: str) -> str:
        if not headline:
            return ""
        normalized = headline.lower().strip()
        normalized = re.sub(r'[!?.,;:]+', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        clickbait_words = [
            'bombshell', 'reveals', 'drops', 'shocking', 'breaking',
            'exclusive', 'urgent', 'watch', 'viral', 'must-see'
        ]
        for word in clickbait_words:
            normalized = normalized.replace(word, '')
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _get_core_keywords(self, headline: str) -> Set[str]:
        normalized = self._normalize_headline(headline)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'was', 'are', 'were', 'this', 'that',
            'after', 'how', 'what', 'why', 'when', 'where'
        }
        words = [word for word in normalized.split() if word not in stop_words and len(word) > 2]
        return set(words)


    def add_story(self, headline: str):
        """Add story to cache with a datetime object."""
        if not headline or len(headline.strip()) < 5:
            return
            
        cache = self._load_cache()
        normalized_key = self._normalize_headline(headline)
        cache[normalized_key] = {
            'timestamp': datetime.now(),
            'original_headline': headline.strip()
        }
        
        self._save_cache(cache)
        print(f"CACHE: Added '{headline[:60]}...'")

    def has_story(self, headline: str, similarity_threshold: float = 0.7) -> bool:
        """
        Check if story exists, now using datetime objects for age comparison.
        """
        if not headline:
            return False
            
        cache = self._load_cache()
        now = datetime.now()
        
        normalized_headline = self._normalize_headline(headline)
        if normalized_headline in cache:
            entry = cache[normalized_headline]
            if (now - entry['timestamp']) < self.max_age:
                print(f"EXACT MATCH: Found cached story '{entry['original_headline'][:50]}...'")
                return True

        new_keywords = self._get_core_keywords(headline)
        if not new_keywords:
            return False

        for cached_key, entry in cache.items():
            if (now - entry['timestamp']) >= self.max_age:
                continue
                
            cached_keywords = self._get_core_keywords(entry['original_headline'])
            if not cached_keywords:
                continue
                
            intersection = new_keywords.intersection(cached_keywords)
            union = new_keywords.union(cached_keywords)
            
            if union:
                similarity = len(intersection) / len(union)
                if similarity >= similarity_threshold:
                    print(f"SIMILAR MATCH ({similarity:.2f}): '{headline[:40]}...' matches '{entry['original_headline'][:40]}...'")
                    return True

        return False

    def prune_cache(self):
        """Remove expired entries using datetime objects."""
        cache = self._load_cache()
        now = datetime.now()
        
        pruned_cache = {
            key: entry for key, entry in cache.items()
            if (now - entry['timestamp']) < self.max_age
        }
        
        MAX_CACHE_SIZE = 1000
        if len(pruned_cache) > MAX_CACHE_SIZE:
            sorted_entries = sorted(
                pruned_cache.items(), 
                key=lambda x: x[1]['timestamp'], 
                reverse=True
            )
            pruned_cache = dict(sorted_entries[:MAX_CACHE_SIZE])
        
        removed_count = len(cache) - len(pruned_cache)
        if removed_count > 0:
            self._save_cache(pruned_cache)
            print(f"CACHE: Pruned {removed_count} old/excess stories.")

    def clear_recent_stories(self, hours: int) -> int:
        """
        NEW: Removes entries younger than the specified number of hours.
        Returns the number of stories cleared.
        """
        if hours <= 0:
            return 0

        cache = self._load_cache()
        now = datetime.now()
        cutoff_time = now - timedelta(hours=hours)
        
        # Keep stories that are OLDER than the cutoff time
        cleared_cache = {
            key: entry for key, entry in cache.items()
            if entry['timestamp'] < cutoff_time
        }
        
        cleared_count = len(cache) - len(cleared_cache)
        if cleared_count > 0:
            self._save_cache(cleared_cache)
            print(f"CACHE: Cleared {cleared_count} stories from the last {hours} hours.")
        
        return cleared_count

    def get_cache_stats(self) -> dict:
        """Get cache statistics using datetime objects."""
        cache = self._load_cache()
        now = datetime.now()
        
        active_stories = sum(
            1 for entry in cache.values()
            if (now - entry['timestamp']) < self.max_age
        )
        
        return {
            'total_entries': len(cache),
            'active_entries': active_stories,
            'expired_entries': len(cache) - active_stories,
            'cache_age_hours': self.max_age.total_seconds() / 3600
        }