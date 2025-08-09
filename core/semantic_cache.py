import chromadb
from typing import List, Optional

class SemanticCache:
    """
    Manages a persistent vector database (ChromaDB) to store and query
    news story embeddings, preventing semantic duplicates.
    """
    
    def __init__(self, path="data/chroma_db", collection_name="news_stories"):
        # Initialize a client that saves data to disk
        self.client = chromadb.PersistentClient(path=path)
        
        # Get or create the collection to store news vectors
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add_story_embedding(self, story_id: str, embedding: List[float]):
        """
        Adds a story's vector embedding to the database.

        Args:
            story_id: A unique identifier for the story (e.g., a hash of its title/URL).
            embedding: The vector representation of the story.
        """
        try:
            self.collection.add(
                embeddings=[embedding],
                ids=[story_id]
            )
            print(f"CACHE: Added semantic fingerprint for story ID {story_id[:10]}...")
        except Exception as e:
            # ChromaDB can sometimes throw errors for duplicate IDs
            print(f"⚠️ Could not add story {story_id[:10]} to semantic cache: {e}")
    
    def is_story_similar(self, new_embedding: List[float], threshold: float = 0.4) -> bool:
        """
        Queries the database to find if a similar story already exists.

        Args:
            new_embedding: The vector of the new story to check.
            threshold: The distance threshold. Lower is more similar. 0.4 is a good starting point.

        Returns:
            True if a similar story is found within the threshold, False otherwise.
        """
        # Only query if the collection is not empty
        if self.collection.count() == 0:
            return False

        # Query for the 1 nearest neighbor
        results = self.collection.query(
            query_embeddings=[new_embedding],
            n_results=1
        )
        
        # 'distances' is a list containing a list of distances for each query
        if results and results['distances'] and results['distances'][0]:
            closest_distance = results['distances'][0][0]
            print(f"🔎 Closest semantic distance found: {closest_distance:.4f} (Threshold: {threshold})")
            
            # If the closest story is within our similarity threshold, it's a duplicate
            if closest_distance < threshold:
                return True
        
        return False

