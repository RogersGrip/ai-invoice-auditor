import json
import shutil
import uuid
import os
from typing import Any, Dict, List
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.core.protocol import Agent, AgentResponse
from src.tools.tools import InvoiceWatcherTool

class InvoiceMonitorAgent(Agent):
    name: str = "Invoice Monitor Agent"
    description: str = "Watchdog that monitors the file system for new invoice files."

    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.json', '.md', '.png', '.jpg', '.jpeg'}

    def __init__(self, watch_dir: str = "data/invoices", processed_dir: str = "data/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.watcher_tool = InvoiceWatcherTool()
        
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _get_sort_key(self, file_path: Path) -> float:
        """Determines sort order based on metadata timestamp or file mtime."""
        meta_path = file_path.with_suffix(".meta.json")
        timestamp = 0.0
        
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                ts_str = data.get("received_timestamp")
                if ts_str:
                    # Handle ISO format with Z
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    timestamp = dt.timestamp()
            except Exception:
                pass
        
        if timestamp == 0.0:
            timestamp = file_path.stat().st_mtime
            
        return timestamp

    def scan(self) -> List[Dict]:
        """
        Scans the watch directory for valid invoice files.
        Returns a sorted list of jobs with metadata.
        """
        jobs = []
        for file_path in self.watch_dir.glob("*.*"):
            # Skip hidden files or metadata files themselves
            if file_path.name.startswith(".") or file_path.suffixes[-2:] == ['.meta', '.json']:
                continue
            
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            # Check for associated metadata
            candidates_path = file_path
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

        # Process oldest files first
        jobs.sort(key=lambda x: x["timestamp"])
        return jobs

    def archive(self, file_path_str: str, dest_name: str = None):
        """Moves processed files and their metadata to the archive folder."""
        source_path = Path(file_path_str)
        if not source_path.exists():
            return

        if not dest_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_name = f"{timestamp}_{source_path.name}"
            
        dest_path = self.processed_dir / dest_name
        
        try:
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived file to: {dest_path}")
            
            # Move metadata if exists
            meta_source = source_path.with_suffix(".meta.json")
            if meta_source.exists():
                meta_dest_name = Path(dest_name).with_suffix(".meta.json").name
                meta_dest = self.processed_dir / meta_dest_name
                shutil.move(str(meta_source), str(meta_dest))
                
        except Exception as e:
            logger.error(f"Failed to archive {source_path.name}: {e}")

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        jobs = self.scan()
        
        if not jobs:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Extractor Agent",
                message_type="RESPONSE",
                payload={"status": "idle", "message": "No new files detected."},
                context_id=None
            )

        # Return the first job found
        job = jobs[0]
        file_path = job["file_path"]
        
        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            source_agent=self.name,
            target_agent="Extractor Agent",
            message_type="TASK_HANDOFF",
            payload={
                "file_path": file_path,
                "timestamp": datetime.now().isoformat(),
                "status": "detected",
                "metadata": job.get("metadata", {})
            },
            context_id=f"ctx_{Path(file_path).name}"
        )