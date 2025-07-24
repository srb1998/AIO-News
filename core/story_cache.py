# core/story_cache.py

import json
import os
import time
from filelock import FileLock

class StoryCache:
    """
    A simple file-based cache to keep track of recently processed story headlines
    to prevent duplicate processing.
    """
    def __init__(self, cache_file='data/story_cache.json', max_age_seconds=172800): # Default: 48 hours
        self.cache_file = cache_file
        self.max_age_seconds = max_age_seconds
        # Use a lock file to prevent race conditions if the app ever runs in parallel
        self.lock = FileLock(f"{self.cache_file}.lock")
        self._ensure_cache_exists()

    def _ensure_cache_exists(self):
        """Creates the cache file and its directory if they don't exist."""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        if not os.path.exists(self.cache_file):
            with self.lock:
                # Initialize with an empty JSON object
                with open(self.cache_file, 'w') as f:
                    json.dump({}, f)

    def _load_cache(self) -> dict:
        """Loads the cache from the JSON file."""
        with self.lock:
            with open(self.cache_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    # If the file is corrupted or empty, return an empty dict
                    return {}

    def _save_cache(self, cache_data: dict):
        """Saves the given dictionary to the cache file."""
        with self.lock:
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

    def add_story(self, headline: str):
        """Adds a story headline to the cache with the current timestamp."""
        cache = self._load_cache()
        cache[headline] = time.time()
        self._save_cache(cache)
        print(f"CACHE: Added '{headline[:60]}...'")

    def has_story(self, headline: str) -> bool:
        """Checks if a story headline is in the cache and has not expired."""
        cache = self._load_cache()
        if headline in cache:
            # Check if the timestamp is still within the valid age
            if (time.time() - cache[headline]) < self.max_age_seconds:
                return True
        return False

    def prune_cache(self):
        """Removes expired (old) entries from the cache to keep it clean."""
        cache = self._load_cache()
        current_time = time.time()
        # Create a new dictionary with only the non-expired items
        pruned_cache = {
            headline: timestamp for headline, timestamp
            in cache.items()
            if (current_time - timestamp) < self.max_age_seconds
        }
        # Only rewrite the file if something was actually removed
        if len(cache) != len(pruned_cache):
            self._save_cache(pruned_cache)
            print(f"CACHE: Pruned {len(cache) - len(pruned_cache)} old stories.")