# ===== FILE: src/adk_agents/monitor_agent.py =====
import uuid
import os
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import shutil

# --- ADK Framework Imports ---
from src.frameworks.google_adk.agents import Agent as ADKAgent
from src.frameworks.google_adk.models import LiteLlm
from src.frameworks.google_adk.tools import BaseTool

from src.core.protocol import AgentResponse
from src.core.logger import logger

# 1. Tool Implementation
class DirectoryScanTool(BaseTool):
    def __init__(self, watch_dir: str):
        super().__init__(name="scan_directory", description="Scans the directory for new invoice files.")
        self.watch_dir = Path(watch_dir)

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        jobs = []
        for file_path in self.watch_dir.glob("*.*"):
            if file_path.name.startswith(".") or file_path.name.endswith(".meta.json"):
                continue
            jobs.append(str(file_path))
        return {"files_found": jobs}

# 2. ADK Monitor Agent
class InvoiceMonitorAgent:
    def __init__(self, watch_dir: str = "data/invoices", processed_dir: str = "data/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure ADK Agent
        self.model = LiteLlm(
            model="bedrock/cohere.command-r-plus-v1:0",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        )
        
        self.adk_agent = ADKAgent(
            name="Invoice Monitor Agent",
            model=self.model,
            instruction="You are a System Watchdog. Your job is to check for new files using 'scan_directory' and report if anything needs processing.",
            tools=[DirectoryScanTool(str(self.watch_dir))]
        )

    def scan(self) -> List[Dict]:
        """
        Direct Helper for the server loop (bypass agent for raw speed in tight loops if needed).
        """
        jobs = []
        for file_path in self.watch_dir.glob("*.*"):
            if file_path.name.startswith(".") or file_path.name.endswith(".meta.json"):
                continue
            jobs.append({
                "file_path": str(file_path),
                "timestamp": file_path.stat().st_mtime,
                "metadata": {}
            })
        return sorted(jobs, key=lambda x: x["timestamp"])

    def archive(self, file_path_str: str, dest_name: str = None):
        source_path = Path(file_path_str)
        if not source_path.exists(): return
        
        if not dest_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_name = f"{timestamp}_{source_path.name}"
            
        dest_path = self.processed_dir / dest_name
        try:
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived file to: {dest_path}")
            
            # Archive metadata if exists
            meta_source = source_path.with_suffix(".meta.json")
            if meta_source.exists():
                meta_dest_name = Path(dest_name).with_suffix(".meta.json").name
                meta_dest = self.processed_dir / meta_dest_name
                shutil.move(str(meta_source), str(meta_dest))
        except Exception as e:
            logger.error(f"Failed to archive {source_path.name}: {e}")

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        # Ask the ADK Agent to check
        response_text = await self.adk_agent.process("Scan the directory and tell me if there are new files.")
        
        # In a real agentic loop, the agent would return a structured decision. 
        # For hybrid compatibility, we use the scan() method if the agent says yes, 
        # or we just grab the first file found.
        
        jobs = self.scan()
        if not jobs:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent="Invoice Monitor Agent",
                target_agent="Orchestrator",
                message_type="STATUS",
                payload={"status": "idle", "agent_thought": response_text},
                context_id=None
            )

        target = jobs[0]
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent="Invoice Monitor Agent",
            target_agent="Extractor Agent",
            message_type="TASK_HANDOFF",
            payload={
                "file_path": target["file_path"],
                "file_name": Path(target["file_path"]).name,
                "timestamp": datetime.now().isoformat(),
                "status": "detected",
                "metadata": target.get("metadata", {})
            },
            context_id=f"ctx_{Path(target['file_path']).name}"
        )

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))