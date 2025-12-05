import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from litellm import embedding
from loguru import logger

class VectorDB:
    def __init__(self):
        # Local Qdrant (File-based persistence)
        self.path = "./data/qdrant_storage"
        self.client = QdrantClient(path=self.path)
        self.collection_name = "invoices"
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v1")
        
        self._init_collection()

    def _init_collection(self):
        if not self.client.collection_exists(self.collection_name):
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )

    def _get_embedding(self, text: str) -> List[float]:
        response = embedding(
            model=self.embedding_model,
            input=[text]
        )
        return response["data"][0]["embedding"]

    def add_document(self, text: str, metadata: Dict[str, Any]):
        logger.info(f"Indexing document: {metadata.get('filename', 'unknown')}")
        vector = self._get_embedding(text)
        
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": text, **metadata}
        )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

    def search(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        query_vector = self._get_embedding(query)
        
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit
        )
        
        return [
            {"text": hit.payload["text"], "score": hit.score, "metadata": hit.payload}
            for hit in response.points
        ]

# Global instance
vector_store = VectorDB()