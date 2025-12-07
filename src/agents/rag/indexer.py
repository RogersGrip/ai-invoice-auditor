from typing import Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.core.protocol import Agent, AgentResponse
from src.database.qdrant_db import vector_store
from src.core.logger import logger

class IndexingAgent(Agent):
    name = "Indexing Agent"
    description = "Parses and indexes invoice documents into the Vector DB."

    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Expects keys: 'text', 'filename', 'metadata'
        """
        text = inputs.get("text", "")
        filename = inputs.get("filename", "unknown")
        meta = inputs.get("metadata", {})
        
        if not text:
            return AgentResponse(content="No text to index.", metadata={"status": "skipped"})

        logger.info(f"Indexing Agent: Processing {filename}")
        logger.info(f"Text Content Snippet: {text[:200]}...")
        
        chunks = self.text_splitter.create_documents([text])
        indexed_count = 0
        
        for i, chunk in enumerate(chunks):
            # Enrich metadata
            chunk_meta = {
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                **meta
            }
            vector_store.add_document(chunk.page_content, chunk_meta)
            indexed_count += 1
            
        logger.success(f"Indexed {indexed_count} chunks for {filename}")
        
        return AgentResponse(
            content=f"Successfully indexed {indexed_count} chunks.", 
            metadata={"chunks": indexed_count}
        )
