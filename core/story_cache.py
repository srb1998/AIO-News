# core/story_cache.py

import json
import os
import time
import re
from typing import Set

class StoryCache:
    """
    IMPROVED: File-based cache with better duplicate detection and automatic pruning
    """
    def __init__(self, cache_file='data/story_cache.json', max_age_seconds=86400): # 24 hours
        self.cache_file = cache_file
        self.max_age_seconds = max_age_seconds
        self._ensure_cache_exists()

    def _ensure_cache_exists(self):
        """Creates cache file and directory if missing"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, 'w') as f:
                json.dump({}, f)

    def _load_cache(self) -> dict:
        """Loads cache with error handling"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_cache(self, cache_data: dict):
        """Saves cache data to file"""
        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

    def _normalize_headline(self, headline: str) -> str:
        """
        NEW: Normalize headlines for better duplicate detection
        Removes common variations that should be considered the same story
        """
        if not headline:
            return ""
        
        # Convert to lowercase for comparison
        normalized = headline.lower().strip()
        
        # Remove common punctuation and extra spaces
        normalized = re.sub(r'[!?.,;:]+', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common clickbait words that create false uniqueness
        clickbait_words = [
            'bombshell', 'reveals', 'drops', 'shocking', 'breaking',
            'exclusive', 'urgent', 'watch', 'viral', 'must-see'
        ]
        
        for word in clickbait_words:
            normalized = normalized.replace(word, '')
        
        # Clean up extra spaces after removals
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized

    def _get_core_keywords(self, headline: str) -> Set[str]:
        """
        Extract core keywords from headline for similarity matching
        """
        normalized = self._normalize_headline(headline)
        
        # Split into words and filter out common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'was', 'are', 'were', 'this', 'that',
            'after', 'how', 'what', 'why', 'when', 'where'
        }
        
        words = [word for word in normalized.split() if word not in stop_words and len(word) > 2]
        return set(words)

    def add_story(self, headline: str):
        """Add story to cache with current timestamp"""
        if not headline or len(headline.strip()) < 5:
            return
            
        cache = self._load_cache()
        normalized_key = self._normalize_headline(headline)
        
        cache[normalized_key] = {
            'timestamp': time.time(),
            'original_headline': headline.strip()
        }
        
        self._save_cache(cache)
        print(f"CACHE: Added '{headline[:60]}...'")

    def has_story(self, headline: str, similarity_threshold: float = 0.7) -> bool:
        """
        IMPROVED: Check if story exists with fuzzy matching for similar headlines
        """
        if not headline:
            return False
            
        cache = self._load_cache()
        current_time = time.time()
        
        # First check exact normalized match
        normalized_headline = self._normalize_headline(headline)
        if normalized_headline in cache:
            entry = cache[normalized_headline]
            if (current_time - entry['timestamp']) < self.max_age_seconds:
                print(f"EXACT MATCH: Found cached story '{entry['original_headline'][:50]}...'")
                return True

        # Then check similarity with all cached stories
        new_keywords = self._get_core_keywords(headline)
        if not new_keywords:
            return False

        for cached_key, entry in cache.items():
            # Skip expired entries
            if (current_time - entry['timestamp']) >= self.max_age_seconds:
                continue
                
            cached_keywords = self._get_core_keywords(entry['original_headline'])
            if not cached_keywords:
                continue
                
            # Calculate keyword overlap similarity
            intersection = new_keywords.intersection(cached_keywords)
            union = new_keywords.union(cached_keywords)
            
            if union:
                similarity = len(intersection) / len(union)
                if similarity >= similarity_threshold:
                    print(f"SIMILAR MATCH ({similarity:.2f}): '{headline[:40]}...' matches '{entry['original_headline'][:40]}...'")
                    return True

        return False

    def prune_cache(self):
        """Remove expired entries and maintain cache size"""
        cache = self._load_cache()
        current_time = time.time()
        
        # Remove expired entries
        pruned_cache = {
            key: entry for key, entry in cache.items()
            if (current_time - entry['timestamp']) < self.max_age_seconds
        }
        
        # If cache is getting too large, remove oldest entries
        MAX_CACHE_SIZE = 1000
        if len(pruned_cache) > MAX_CACHE_SIZE:
            # Sort by timestamp and keep the most recent entries
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

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring"""
        cache = self._load_cache()
        current_time = time.time()
        
        active_stories = sum(
            1 for entry in cache.values()
            if (current_time - entry['timestamp']) < self.max_age_seconds
        )
        
        return {
            'total_entries': len(cache),
            'active_entries': active_stories,
            'expired_entries': len(cache) - active_stories,
            'cache_age_hours': self.max_age_seconds / 3600
        }