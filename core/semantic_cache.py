# core/semantic_cache.py

import chromadb
from typing import List, Optional
import time

class SemanticCache:
    """
    IMPROVED: Better similarity detection and cache management for news stories
    """
    
    def __init__(self, path="data/chroma_db", collection_name="news_stories"):
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add_story_embedding(self, story_id: str, embedding: List[float], metadata: dict = None):
        """
        ENHANCED: Add story with metadata for better tracking
        """
        try:
            # Add timestamp to metadata for potential cleanup
            story_metadata = metadata or {}
            story_metadata['timestamp'] = time.time()
            
            self.collection.add(
                embeddings=[embedding],
                ids=[story_id],
                metadatas=[story_metadata]
            )
            print(f"SEMANTIC CACHE: Added fingerprint for {story_id[:12]}...")
        except Exception as e:
            # Handle duplicate IDs gracefully
            if "already exists" in str(e).lower():
                print(f"SEMANTIC CACHE: Story {story_id[:12]} already cached")
            else:
                print(f"⚠️ Semantic cache error for {story_id[:12]}: {e}")
    
    def is_story_similar(self, new_embedding: List[float], threshold: float = 0.38) -> bool:
        """
        IMPROVED: Better similarity detection with adaptive thresholds
        """
        if self.collection.count() == 0:
            return False

        try:
            # Query for top 3 nearest neighbors for better comparison
            results = self.collection.query(
                query_embeddings=[new_embedding],
                n_results=min(3, self.collection.count())
            )
            
            if not results or not results.get('distances') or not results['distances'][0]:
                return False

            distances = results['distances'][0]
            closest_distance = distances[0]
            
            print(f"🔍 Semantic distances: {[f'{d:.3f}' for d in distances[:3]]} (threshold: {threshold})")
            
            # Enhanced logic: Consider a story similar if:
            # 1. Very close match (< 0.30)
            # 2. Multiple similar stories exist (indicates trending topic)
            if closest_distance < 0.30:
                print(f"🎯 Very similar story found (distance: {closest_distance:.3f})")
                return True
            
            elif closest_distance < threshold:
                # Check if multiple similar stories exist (trending topic detection)
                similar_count = sum(1 for d in distances if d < threshold + 0.1)
                if similar_count >= 2:
                    print(f"📈 Trending topic detected ({similar_count} similar stories)")
                    return True
                else:
                    print(f"✅ Story unique enough (distance: {closest_distance:.3f})")
                    return False
            
            return False
            
        except Exception as e:
            print(f"❌ Semantic similarity check failed: {e}")
            return False

    def get_similar_stories(self, embedding: List[float], limit: int = 5) -> List[dict]:
        """
        NEW: Get similar stories for analysis/debugging
        """
        if self.collection.count() == 0:
            return []

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=min(limit, self.collection.count()),
                include=['distances', 'metadatas']
            )
            
            similar_stories = []
            if results and results.get('distances') and results.get('metadatas'):
                for i, distance in enumerate(results['distances'][0]):
                    if i < len(results['metadatas'][0]):
                        similar_stories.append({
                            'distance': distance,
                            'metadata': results['metadatas'][0][i]
                        })
            
            return similar_stories
            
        except Exception as e:
            print(f"❌ Error getting similar stories: {e}")
            return []

    def cleanup_old_entries(self, max_age_seconds: int = 172800):  # 48 hours
        """
        NEW: Clean up old entries to prevent cache bloat
        Note: ChromaDB doesn't have built-in TTL, so this is a manual cleanup
        """
        try:
            current_time = time.time()
            
            # Get all entries with metadata
            all_results = self.collection.get(include=['metadatas'])
            
            if not all_results or not all_results.get('ids'):
                return
            
            old_ids = []
            for i, story_id in enumerate(all_results['ids']):
                metadata = all_results.get('metadatas', [{}])[i] if i < len(all_results.get('metadatas', [])) else {}
                timestamp = metadata.get('timestamp', current_time)  # Default to current if no timestamp
                
                if (current_time - timestamp) > max_age_seconds:
                    old_ids.append(story_id)
            
            if old_ids:
                self.collection.delete(ids=old_ids)
                print(f"🧹 Cleaned up {len(old_ids)} old semantic cache entries")
                
        except Exception as e:
            print(f"❌ Semantic cache cleanup failed: {e}")

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            total_count = self.collection.count()
            return {
                'total_embeddings': total_count,
                'collection_name': self.collection.name
            }
        except Exception as e:
            print(f"❌ Error getting semantic cache stats: {e}")
            return {'total_embeddings': 0, 'collection_name': 'unknown'}