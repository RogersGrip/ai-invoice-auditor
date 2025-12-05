import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from litellm import embedding
from loguru import logger
from src.core.config import settings
from src.rag_engine.schema import RetrievedChunk

class QdrantHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QdrantHandler, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.client = QdrantClient(path=settings.QDRANT_PATH)
        self.collection_name = "invoice_knowledge_base"
        self.embedding_model = settings.EMBEDDING_MODEL
        self.vector_size = 1536 # Default for Titan V1. Adjust if using Cohere (1024)
        self._ensure_collection()

    def _ensure_collection(self):
        if not self.client.collection_exists(self.collection_name):
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
            )

    def get_embedding(self, text: str) -> List[float]:
        try:
            response = embedding(
                model=self.embedding_model,
                input=[text]
            )
            return response["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def upsert_vectors(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        points = []
        for text, meta in zip(texts, metadatas):
            vector = self.get_embedding(text)
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"text": text, **meta}
            ))
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        logger.info(f"Indexed {len(points)} chunks into Qdrant.")

    def search(self, query: str, limit: int = 5) -> List[RetrievedChunk]:
        query_vector = self.get_embedding(query)
        hits = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit
        ).points

        results = []
        for i, hit in enumerate(hits):
            results.append(RetrievedChunk(
                text=hit.payload.get("text", ""),
                score=hit.score,
                metadata=hit.payload,
                rank=i + 1
            ))
        return results

vector_store = QdrantHandler()