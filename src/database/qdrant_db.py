import uuid
import os
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from litellm import embedding
from src.core.config import settings
from src.core.logger import logger

class VectorDB:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorDB, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Do not initialize client here to avoid file lock on import
        self.collection_name = "invoices"
        self.embedding_model = settings.EMBEDDING_MODEL

    def _get_client(self):
        if self._client is None:
            try:
                self._client = QdrantClient(path=str(settings.QDRANT_PATH))
            except Exception as e:
                logger.warning(f"Qdrant Init Retry: {e}")
                time.sleep(1)
                self._client = QdrantClient(path=str(settings.QDRANT_PATH))
        return self._client

    def _ensure_collection(self, vector_size: int = 1536):
        client = self._get_client()
        if not client.collection_exists(self.collection_name):
            logger.info(f"Creating Collection '{self.collection_name}'")
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )

    def _get_embedding(self, text: str) -> List[float]:
        try:
            response = embedding(model=self.embedding_model, input=[text])
            data = response.data[0]
            return data['embedding'] if isinstance(data, dict) else data.embedding
        except Exception as e:
            logger.error(f"Embedding Failed: {e}")
            return []

    def add_document(self, text: str, metadata: Dict[str, Any]) -> str:
        vector = self._get_embedding(text)
        if not vector: return ""
        
        self._ensure_collection(vector_size=len(vector))
        client = self._get_client()
        point_id = str(uuid.uuid4())
        
        try:
            client.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=point_id, vector=vector, payload={"text": text, **metadata})]
            )
            return point_id
        except Exception as e:
            if "wrong vector size" in str(e).lower() or "broadcast" in str(e).lower():
                logger.warning("Dimension Mismatch. Recreating DB...")
                client.delete_collection(self.collection_name)
                self._ensure_collection(vector_size=len(vector))
                client.upsert(
                    collection_name=self.collection_name,
                    points=[PointStruct(id=point_id, vector=vector, payload={"text": text, **metadata})]
                )
                return point_id
            raise e

    def search(self, query: str, limit: int = 5, filename: Optional[str] = None) -> List[Dict]:
        self._ensure_collection()
        client = self._get_client()
        vector = self._get_embedding(query)
        if not vector: return []

        qf = Filter(must=[FieldCondition(key="filename", match=MatchValue(value=filename))]) if filename else None
        
        try:
            res = client.query_points(self.collection_name, query=vector, query_filter=qf, limit=limit)
            return [{"text": h.payload.get("text"), "score": h.score, "metadata": h.payload} for h in res.points]
        except: return []

vector_store = VectorDB()