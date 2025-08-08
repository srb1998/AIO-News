# core/semantic_cache.py - IMPROVED VERSION

import chromadb
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

class SemanticCache:
    """
    Enhanced semantic cache with time-based expiry and better duplicate detection.
    """
    
    def __init__(self, path="data/chroma_db", collection_name="news_stories", expiry_hours=48):
        # Initialize a client that saves data to disk
        self.client = chromadb.PersistentClient(path=path)
        self.expiry_hours = expiry_hours
        
        # Get or create the collection to store news vectors
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine distance for better semantic similarity
        )

    def add_story_embedding(self, story_id: str, embedding: List[float], metadata: Dict[str, Any] = None):
        """
        Adds a story's vector embedding to the database with timestamp.

        Args:
            story_id: A unique identifier for the story
            embedding: The vector representation of the story
            metadata: Additional metadata (title, source, etc.)
        """
        try:
            # Add timestamp and metadata
            story_metadata = {
                "timestamp": datetime.now().isoformat(),
                "title": metadata.get("title", "") if metadata else "",
                "source": metadata.get("source", "") if metadata else "",
            }
            
            self.collection.add(
                embeddings=[embedding],
                ids=[story_id],
                metadatas=[story_metadata]
            )
            print(f"CACHE: Added semantic fingerprint for story ID {story_id[:10]}...")
        except Exception as e:
            # ChromaDB can sometimes throw errors for duplicate IDs
            print(f"⚠️ Could not add story {story_id[:10]} to semantic cache: {e}")
    
    def is_story_similar(self, new_embedding: List[float], threshold: float = 0.4) -> bool:
        """
        Queries the database to find if a similar story already exists.
        Now considers time-based expiry.

        Args:
            new_embedding: The vector of the new story to check
            threshold: The distance threshold for similarity

        Returns:
            True if a similar non-expired story is found, False otherwise
        """
        # Clean expired stories first
        self._cleanup_expired_stories()
        
        # Only query if the collection is not empty
        if self.collection.count() == 0:
            return False

        # Query for the 3 nearest neighbors (in case closest is expired)
        results = self.collection.query(
            query_embeddings=[new_embedding],
            n_results=min(3, self.collection.count())
        )
        
        if results and results['distances'] and results['distances'][0]:
            for i, distance in enumerate(results['distances'][0]):
                print(f"🔎 Checking similarity #{i+1}: distance {distance:.4f} (Threshold: {threshold})")
                
                # Check if this result is within threshold
                if distance < threshold:
                    # Check if this story is expired
                    metadata = results['metadatas'][0][i] if results.get('metadatas') and results['metadatas'][0] else {}
                    timestamp_str = metadata.get('timestamp')
                    
                    if timestamp_str:
                        try:
                            story_timestamp = datetime.fromisoformat(timestamp_str)
                            if datetime.now() - story_timestamp < timedelta(hours=self.expiry_hours):
                                print(f"📚 Found similar recent story (age: {(datetime.now() - story_timestamp).total_seconds()/3600:.1f}h)")
                                return True
                            else:
                                print(f"⏰ Similar story found but expired (age: {(datetime.now() - story_timestamp).total_seconds()/3600:.1f}h)")
                        except:
                            # If timestamp parsing fails, assume it's recent
                            return True
                    else:
                        # No timestamp metadata, assume it's recent
                        return True
        
        return False

    def _cleanup_expired_stories(self):
        """Remove expired stories from the cache"""
        try:
            # Get all stories
            all_results = self.collection.get()
            
            if not all_results or not all_results.get('metadatas'):
                return
            
            expired_ids = []
            cutoff_time = datetime.now() - timedelta(hours=self.expiry_hours)
            
            for i, metadata in enumerate(all_results['metadatas']):
                if metadata and metadata.get('timestamp'):
                    try:
                        story_timestamp = datetime.fromisoformat(metadata['timestamp'])
                        if story_timestamp < cutoff_time:
                            story_id = all_results['ids'][i]
                            expired_ids.append(story_id)
                    except:
                        continue
            
            # Delete expired stories
            if expired_ids:
                self.collection.delete(ids=expired_ids)
                print(f"🗑️ Cleaned up {len(expired_ids)} expired stories from cache")
        
        except Exception as e:
            print(f"⚠️ Cache cleanup failed: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache"""
        try:
            total_count = self.collection.count()
            
            # Get recent vs old stories
            recent_count = 0
            if total_count > 0:
                results = self.collection.get()
                cutoff_time = datetime.now() - timedelta(hours=self.expiry_hours)
                
                for metadata in results.get('metadatas', []):
                    if metadata and metadata.get('timestamp'):
                        try:
                            story_timestamp = datetime.fromisoformat(metadata['timestamp'])
                            if story_timestamp >= cutoff_time:
                                recent_count += 1
                        except:
                            recent_count += 1  # Count unparseable as recent
            
            return {
                "total_stories": total_count,
                "recent_stories": recent_count,
                "expired_stories": total_count - recent_count,
                "expiry_hours": self.expiry_hours
            }
        except Exception as e:
            print(f"⚠️ Could not get cache stats: {e}")
            return {"error": str(e)}

    def clear_cache(self):
        """Clear all cached stories (useful for testing)"""
        try:
            # Delete the collection and recreate it
            self.client.delete_collection(name=self.collection.name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection.name,
                metadata={"hnsw:space": "cosine"}
            )
            print("🗑️ Cache cleared successfully")
        except Exception as e:
            print(f"⚠️ Could not clear cache: {e}")