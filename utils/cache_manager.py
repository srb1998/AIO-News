# FILE: utils/cache_manager.py

import json
import os
import time
from typing import Any, Optional
from datetime import datetime, timedelta

class CacheManager:
    """
    Simple file-based caching to save API calls and improve performance
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        """Get file path for cache key"""
        # Create safe filename from key
        safe_key = "".join(c for c in key if c.isalnum() or c in ('-', '_'))[:50]
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def get(self, key: str, expire_hours: int = 24) -> Optional[Any]:
        """
        Get cached data if it exists and hasn't expired
        
        Args:
            key: Cache key
            expire_hours: Hours after which cache expires
        
        Returns:
            Cached data or None if not found/expired
        """
        try:
            cache_path = self._get_cache_path(key)
            
            if not os.path.exists(cache_path):
                return None
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache has expired
            cached_time = cache_data.get('timestamp', 0)
            expire_time = cached_time + (expire_hours * 3600)  # Convert hours to seconds
            
            if time.time() > expire_time:
                # Cache expired, remove file
                os.remove(cache_path)
                return None
            
            return cache_data.get('data')
            
        except Exception as e:
            print(f"❌ Cache get error for key '{key}': {e}")
            return None
    
    def set(self, key: str, data: Any, expire_hours: int = 24):
        """
        Set cached data
        
        Args:
            key: Cache key
            data: Data to cache
            expire_hours: Hours after which cache should expire
        """
        try:
            cache_path = self._get_cache_path(key)
            
            cache_data = {
                'timestamp': time.time(),
                'expire_hours': expire_hours,
                'data': data
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Cached data for key: {key}")
            
        except Exception as e:
            print(f"❌ Cache set error for key '{key}': {e}")
    
    def delete(self, key: str):
        """Delete cached data"""
        try:
            cache_path = self._get_cache_path(key)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                print(f"🗑️ Deleted cache for key: {key}")
        except Exception as e:
            print(f"❌ Cache delete error for key '{key}': {e}")
    
    def clear_expired(self):
        """Clear all expired cache files"""
        try:
            if not os.path.exists(self.cache_dir):
                return
            
            cleared_count = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.cache_dir, filename)
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                        
                        cached_time = cache_data.get('timestamp', 0)
                        expire_hours = cache_data.get('expire_hours', 24)
                        expire_time = cached_time + (expire_hours * 3600)
                        
                        if time.time() > expire_time:
                            os.remove(filepath)
                            cleared_count += 1
                            
                    except Exception:
                        # If we can't read the file, delete it
                        os.remove(filepath)
                        cleared_count += 1
            
            if cleared_count > 0:
                print(f"🧹 Cleared {cleared_count} expired cache files")
                
        except Exception as e:
            print(f"❌ Cache cleanup error: {e}")
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            if not os.path.exists(self.cache_dir):
                return {"total_files": 0, "total_size_mb": 0}
            
            total_files = 0
            total_size = 0
            
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.cache_dir, filename)
                    total_files += 1
                    total_size += os.path.getsize(filepath)
            
            return {
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            print(f"❌ Cache stats error: {e}")
            return {"total_files": 0, "total_size_mb": 0}

# Global cache manager instance
cache_manager = CacheManager()