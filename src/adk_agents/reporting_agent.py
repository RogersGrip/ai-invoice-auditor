# ===== FILE: src/adk_agents/reporting_agent.py =====
import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from src.adk_agents.base_agent import AgentADK
from src.core.protocol import AgentResponse
from src.tools.tools import InsightReporterTool

class ReportingAgent(AgentADK):
    def __init__(self):
        super().__init__(
            name="reporting_agent",
            instruction="Generate reports.", 
            tools=[InsightReporterTool()]
        )
        self.reporter_tool = InsightReporterTool()

    # Async method for the graph
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        try:
            # Run tool directly for speed/determinism
            res = self.reporter_tool.run({
                "file_name": inputs.get("file_name", "report"),
                "extracted_data": inputs.get("extracted_data", {}),
                "validation_report": inputs.get("validation_results", {}),
                "safety_report": inputs.get("safety_report", {}),
                "metadata": inputs.get("metadata", {})
            })
            return AgentResponse(
                id=str(uuid.uuid4()), source_agent=self.name, target_agent="Ingestion",
                timestamp=datetime.now(timezone.utc).isoformat(), message_type="RESPONSE",
                payload=res, context_id=inputs.get("context_id")
            )
        except Exception as e:
            return AgentResponse(
                id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc).isoformat(), 
                source_agent=self.name, target_agent="Error", message_type="ERROR", 
                payload={"error": str(e)}
            )

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))