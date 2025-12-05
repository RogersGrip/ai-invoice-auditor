from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class RAGDocument(BaseModel):
    content: str
    metadata: Dict[str, Any]
    doc_id: Optional[str] = None

class RetrievalQuery(BaseModel):
    query_text: str
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None

class RetrievedChunk(BaseModel):
    text: str
    score: float
    metadata: Dict[str, Any]
    rank: int = 0

class GenerationRequest(BaseModel):
    query: str
    context_chunks: List[RetrievedChunk]

class RAGResponse(BaseModel):
    answer: str
    context_used: List[RetrievedChunk]
    confidence_score: float = 0.0

class EvaluationMetric(BaseModel):
    name: str  # e.g., "answer_relevance"
    score: float
    reason: str

class EvaluationReport(BaseModel):
    metrics: List[EvaluationMetric]
    overall_score: float
    is_passing: bool