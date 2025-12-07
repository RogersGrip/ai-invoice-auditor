import json
import shutil
import uuid
from typing import Any, Dict
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.core.protocol import Agent, AgentResponse, AgentTool
from src.tools.tools import InvoiceWatcherTool

class InvoiceMonitorAgent(Agent):
    name = "Invoice Monitor Agent"
    description = "Watchdog that monitors the file system for new invoice files."

    def __init__(self, watch_dir: str = "data/invoices", processed_dir: str = "data/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.watcher_tool = InvoiceWatcherTool()
        
        # Ensure directories exist
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    @property
    def inputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "description": "Polling agent, no specific inputs required."
        }

    @property
    def outputs_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "status": {"type": "string"}
            }
        }

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Scans and returns the next available file as a task.
        Request inputs are ignored as this is a polling agent usually.
        """
        self.start_as_current_observation(inputs)
        # 1. Scan for jobs
        # For strict tool usage, we could call watcher_tool.run() but logic is internal here for now or we wrap it.
        # Let's keep the logic here for efficiency but return standard response using tool schema concepts if needed.
        
        jobs = self.scan()
        
        if not jobs:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Extractor Agent",
                message_type="RESPONSE", # Or NO_OP
                payload={"status": "idle", "message": "No new files detected."},
                context_id=None
            )

        # Pick the high priority job
        job = jobs[0]
        file_path = job["file_path"]
        
        # 2. Archive it immediately to avoid double processing (Optimistic locking)
        # In a real event bus, we might wait for ack, but here we move to processed.
        # Actually, if we archive now, the Extractor needs the path in processed folder?
        # Or we keep in inbox and move after? Let's assume we move to 'processing' state or just pass path.
        # AGENTS.md says Handoff to Extractor.
        
        # Let's simple check if we should move it. 
        # For this implementation, let's pass the file path.
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent=self.name,
            target_agent="Extractor Agent",
            message_type="TASK_HANDOFF",
            payload={
                "file_path": file_path, 
                "timestamp": datetime.now().isoformat(),
                "status": "detected"
            },
            context_id=f"ctx_{Path(file_path).name}"
        )

    # ... Helper methods ...
    # Define supported extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.json', '.md', '.png', '.jpg', '.jpeg'}

    def _get_sort_key(self, file_path: Path) -> float:
        """
        Determines priority based on timestamp.
        Priority: 1. Metadata 'received_timestamp' (ISO) 2. File System Modified Time
        """
        meta_path = file_path.with_suffix(".meta.json")
        timestamp = 0.0

        # 1. Try Metadata Timestamp
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                ts_str = data.get("received_timestamp")
                if ts_str:
                    # Parse ISO string to float timestamp
                    # Handles flexible ISO formats (e.g. 2025-05-02T11:00:00Z)
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    timestamp = dt.timestamp()
            except Exception:
                pass # Fallback to file time on error
        
        # 2. Fallback to File System Time
        if timestamp == 0.0:
            timestamp = file_path.stat().st_mtime
            
        return timestamp

    def scan(self) -> list[dict]:
        """
        Scans the inbox for all valid files, sorts them by time, and returns jobs.
        """
        jobs = []
        
        # 1. Gather all candidates
        for file_path in self.watch_dir.glob("*.*"):
            # Skip hidden, metadata files, and unsupported types
            if (file_path.name.startswith(".") or 
                file_path.suffixes[-2:] == ['.meta', '.json']):
                continue
            
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
                
            candidates_path = file_path
            # Check for metadata
            meta_path = candidates_path.with_suffix(".meta.json")
            metadata = {}
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            jobs.append({
                "file_path": str(candidates_path),
                "timestamp": self._get_sort_key(candidates_path),
                "metadata": metadata
            })

        # 2. Sort candidates by timestamp (Oldest First - FIFO)
        jobs.sort(key=lambda x: x["timestamp"])
            
        return jobs

    def archive(self, file_path_str: str, dest_name: str = None):
        """
        Moves the invoice and its metadata to the 'processed' folder.
        """
        source_path = Path(file_path_str)
        if not source_path.exists():
            return

        # 1. Define Destination
        if not dest_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_name = f"{timestamp}_{source_path.name}"
            
        dest_path = self.processed_dir / dest_name

        try:
            # 2. Move Main File
            # Check if destination exists to avoid overwrite error or handle it
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived file to: {dest_path}")

            # 3. Move Metadata File (if exists)
            meta_source = source_path.with_suffix(".meta.json")
            if meta_source.exists():
                meta_dest_name = Path(dest_name).with_suffix(".meta.json").name
                meta_dest = self.processed_dir / meta_dest_name
                
                shutil.move(str(meta_source), str(meta_dest))
                
        except Exception as e:
            logger.error(f"Failed to archive {source_path.name}: {e}")