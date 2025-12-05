from typing import Dict, Any, List
from src.rag_engine.tools import (
    VectorIndexerTool, 
    SemanticRetrieverTool, 
    ChunkRankerTool, 
    ResponseSynthesizerTool, 
    RAGEvaluatorTool
)
from src.rag_engine.schema import RAGResponse, RetrievedChunk
from loguru import logger

# 1. Indexing Agent
class IndexingAgent:
    def __init__(self):
        self.tool = VectorIndexerTool()

    def ingest(self, text: str, metadata: Dict[str, Any]) -> str:
        logger.info(f"Indexing Agent: Processing {metadata.get('filename')}")
        return self.tool.process(text, metadata)

# 2. Retrieval Agent
class RetrievalAgent:
    def __init__(self):
        self.tool = SemanticRetrieverTool()

    def retrieve(self, query: str) -> List[RetrievedChunk]:
        logger.info(f"Retrieval Agent: Searching for '{query}'")
        return self.tool.process(query)

# 3. Augmentation Agent (Reranker)
class AugmentationAgent:
    def __init__(self):
        self.tool = ChunkRankerTool()

    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        logger.info("Augmentation Agent: Re-ranking chunks")
        return self.tool.process(query, chunks)

# 4. Generation Agent
class GenerationAgent:
    def __init__(self):
        self.tool = ResponseSynthesizerTool()

    def generate(self, query: str, chunks: List[RetrievedChunk]) -> str:
        logger.info("Generation Agent: Synthesizing answer")
        return self.tool.process(query, chunks)

# 5. Reflection Agent
class ReflectionAgent:
    def __init__(self):
        self.tool = RAGEvaluatorTool()

    def evaluate(self, query: str, answer: str, chunks: List[RetrievedChunk]):
        logger.info("Reflection Agent: Evaluating response quality")
        return self.tool.process(query, answer, chunks)

# Orchestrator (The "RAG Pipeline")
class RAGOrchestrator:
    def __init__(self):
        self.indexer = IndexingAgent()
        self.retriever = RetrievalAgent()
        self.augmenter = AugmentationAgent()
        self.generator = GenerationAgent()
        self.reflector = ReflectionAgent()

    def add_knowledge(self, text: str, metadata: Dict[str, Any]):
        return self.indexer.ingest(text, metadata)

    def ask(self, query: str) -> Dict[str, Any]:
        # 1. Retrieve
        chunks = self.retriever.retrieve(query)
        
        # 2. Augment (Rerank)
        ranked_chunks = self.augmenter.rerank(query, chunks)
        
        # 3. Generate
        answer = self.generator.generate(query, ranked_chunks)
        
        # 4. Reflect (Evaluate)
        eval_report = self.reflector.evaluate(query, answer, ranked_chunks)
        
        return {
            "answer": answer,
            "context": [c.model_dump() for c in ranked_chunks],
            "evaluation": eval_report.model_dump()
        }

rag_system = RAGOrchestrator()