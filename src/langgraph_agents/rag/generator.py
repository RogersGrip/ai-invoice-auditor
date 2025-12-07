import os
import uuid
from datetime import datetime
from typing import Dict, Any
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from langfuse import observe
from src.tools.tools import ResponseSynthesizerTool

class GenerationAgent(Agent):
    name = "Generation Agent"
    description = "Generates natural language answers using retrieved context."

    def __init__(self):
        self.synthesizer_tool = ResponseSynthesizerTool()

    @observe(name="GenerationAgent.process")
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        payload = inputs.get("payload", {})
        query = inputs.get("query") or payload.get("query")
        context = inputs.get("context") or payload.get("context", "")
        
        if not query:
             return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No query provided"},
                 context_id=inputs.get("context_id")
             )
        
        try:
            logger.info(f"Generation Agent: Synthesizing answer...")
            
            output = self.synthesizer_tool.run(query, context)
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                timestamp=datetime.now().isoformat(),
                target_agent="Reflection Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "answer": output,
                    "query": query,
                    "context": context
                },
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
             )
