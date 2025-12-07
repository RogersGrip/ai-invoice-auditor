import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from litellm import embedding
from src.core.config import settings
from src.core.logger import logger

class VectorDB:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorDB, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize attributes that don't depend on networking
        self.collection_name = "invoices"
        self.embedding_model = settings.EMBEDDING_MODEL

    def _get_client(self):
        """Creates a fresh client instance. Must be closed after use."""
        # Force location to be disk-based always
        return QdrantClient(path=str(settings.QDRANT_PATH))

    def _init_db(self):
        """Ensures collection exists. Uses a transient client."""
        logger.info(f"Checking Qdrant collection at {settings.QDRANT_PATH}")
        client = self._get_client()
        try:
            # Attributes are now set in __init__
            
            if not client.collection_exists(self.collection_name):
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                
                # Determine vector size based on model
                vec_size = 768 if "nomic" in self.embedding_model or settings.MODEL_PROVIDER == "ollama" else 1024
                
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vec_size, distance=Distance.COSINE)
                )
        finally:
            client.close()

    def _get_embedding(self, text: str) -> List[float]:
        try:
            model = settings.EMBEDDING_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model = f"ollama/{settings.OLLAMA_EMBEDDING_MODEL}"

            response = embedding(
                model=model,
                input=[text]
            )
            # Litellm response object access (handles both object and dict)
            # Litellm response object access (handles both object and dict)
            data_item = response.data[0]
            if isinstance(data_item, dict):
                return data_item['embedding']
            elif hasattr(data_item, 'embedding'):
                return data_item.embedding
            else:
                # Fallback for some provider responses
                return data_item[0]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []

    def close(self):
        pass # No-op now as we use transient connections

    def add_document(self, text: str, metadata: Dict[str, Any]) -> str:
        """
        Indexes a document chunk.
        """
        vector = self._get_embedding(text)
        point_id = str(uuid.uuid4())
        
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload={"text": text, **metadata} 
        )
        
        client = self._get_client()
        try:
            try:
                client.upsert(
                    collection_name=self.collection_name,
                    points=[point]
                )
            except Exception as e:
                # If collection missing, try to init and retry once
                if "not found" in str(e).lower() or "not exist" in str(e).lower():
                    logger.warning(f"Collection '{self.collection_name}' missing. Attempting to create.")
                    self._init_db()
                    
                    # Re-open client as _init_db closes its own
                    # But we are in a finally block... wait.
                    # _init_db uses its own context.
                    # The current 'client' is still open.
                    
                    client.upsert(
                        collection_name=self.collection_name,
                        points=[point]
                    )
                else:
                    raise e
        finally:
            client.close()
            
        return point_id

    def search(self, query: str, limit: int = 5, filename: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Semantic search with optional filename filtering.
        """
        query_vector = self._get_embedding(query)
        
        query_filter = None
        if filename:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="filename",
                        match=MatchValue(value=filename)
                    )
                ]
            )

        client = self._get_client()
        try:
            response = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit
            )
            
            return [
                {
                    "text": hit.payload.get("text"), 
                    "score": hit.score, 
                    "metadata": {k:v for k,v in hit.payload.items() if k != 'text'}
                }
                for hit in response.points
            ]
        finally:
            client.close()

# Singleton
vector_store = VectorDB()