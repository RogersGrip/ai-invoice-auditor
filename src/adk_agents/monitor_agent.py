import uuid
import shutil
import os
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

from src.adk_agents.base_agent import AgentADK
from google.adk.tools import BaseTool
from google.genai.types import FunctionDeclaration, Schema, Type
from src.core.protocol import AgentResponse
from src.core.logger import logger

class DirectoryScanTool(BaseTool):
    def __init__(self, watch_dir: str):
        super().__init__(name="scan_directory", description="Scans folder for new files.")
        self.watch_dir = Path(watch_dir)

    def _get_declaration(self):
        return FunctionDeclaration(name=self.name, description=self.description, parameters=Schema(type=Type.OBJECT, properties={}))

    def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        jobs = []
        for f in self.watch_dir.glob("*.*"):
            if not f.name.startswith(".") and not f.name.endswith(".meta.json"):
                jobs.append(str(f))
        return {"files_found": jobs}

class InvoiceMonitorAgent(AgentADK):
    def __init__(self, watch_dir: str = "data/invoices", processed_dir: str = "data/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        super().__init__(
            name="invoice_monitor_agent",
            instruction="You are a Watchdog. Check for new files.",
            tools=[DirectoryScanTool(str(self.watch_dir))]
        )

    def scan(self) -> List[Dict]:
        """Direct helper for high-frequency server polling."""
        jobs = []
        # logger.debug(f"Scanning directory: {self.watch_dir.resolve()}")
        
        if not self.watch_dir.exists():
            logger.warning(f"Watch directory does not exist: {self.watch_dir}")
            return []

        for f in self.watch_dir.glob("*.*"):
            # Logging to debug why files might be skipped
            # logger.debug(f"Found file: {f.name}")
            
            if f.name.startswith("."):
                # logger.debug(f"Skipping hidden file: {f.name}")
                continue
                
            if f.name.endswith(".meta.json"):
                # logger.debug(f"Skipping meta file: {f.name}")
                continue
                
            # Valid file found
            jobs.append({"file_path": str(f), "timestamp": f.stat().st_mtime, "metadata": {}})
            
        if jobs:
            jobs.sort(key=lambda x: x["timestamp"])
            
        return jobs

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))

    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        await self.run("Check for files.") 
        jobs = self.scan()
        if not jobs:
            return AgentResponse(
                id=str(uuid.uuid4()), timestamp=datetime.now().isoformat(),
                source_agent=self.name, target_agent="Orchestrator",
                message_type="STATUS", payload={"status": "idle"}, context_id=None
            )
        target = jobs[0]
        return AgentResponse(
            id=str(uuid.uuid4()), timestamp=datetime.now().isoformat(),
            source_agent=self.name, target_agent="Extractor Agent",
            message_type="TASK_HANDOFF",
            payload={
                "file_path": target["file_path"], "file_name": Path(target["file_path"]).name,
                "timestamp": datetime.now().isoformat(), "status": "detected", "metadata": {}
            },
            context_id=f"ctx_{Path(target['file_path']).name}"
        )

    def archive(self, file_path_str: str, dest_name: str = None):
        source = Path(file_path_str)
        if not source.exists(): return
        dest = self.processed_dir / (dest_name or f"{source.name}")
        try:
            shutil.move(str(source), str(dest))
            logger.info(f"Archived to {dest}")
            meta = source.with_suffix(".meta.json")
            if meta.exists(): shutil.move(str(meta), str(self.processed_dir / Path(dest.name).with_suffix(".meta.json").name))
        except Exception as e: logger.error(f"Archive failed: {e}")