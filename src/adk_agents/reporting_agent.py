# ===== FILE: src/adk_agents/reporting_agent.py =====
import uuid
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone
from src.adk_agents.base_agent import AgentADK
from src.core.protocol import AgentResponse
from src.tools.tools import InsightReporterTool
from src.core.logger import logger

class ReportingAgent(AgentADK):
    def __init__(self):
        super().__init__(
            name="reporting_agent",
            instruction="Generate detailed audit reports including safety and HITL approval context.",
            tools=[InsightReporterTool()]
        )
        self.reporter_tool = InsightReporterTool()

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        try:
            logger.info("ReportingAgent: Generating report...")
            
            # Extract inputs including new approval info
            file_name = inputs.get("file_name", "unknown_report")
            data = inputs.get("extracted_data") or {}
            val_results = inputs.get("validation_results") or {}
            safety = inputs.get("safety_report") or {}
            meta = inputs.get("metadata") or {}
            approval = inputs.get("approval_info") or None

            # Execute Tool with approval context
            res = self.reporter_tool.run({
                "file_name": file_name,
                "extracted_data": data,
                "validation_report": val_results,
                "safety_report": safety,
                "metadata": meta,
                "approval_info": approval
            })
            
            logger.info(f"Report Generated: {res}")
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                source_agent=self.name,
                target_agent="Ingestion",
                timestamp=datetime.now(timezone.utc).isoformat(),
                message_type="RESPONSE",
                payload=res,
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.error(f"Reporting Agent Failed: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Error",
                message_type="ERROR",
                payload={"error": str(e)}
            )

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        return asyncio.run(self.process_async(inputs))