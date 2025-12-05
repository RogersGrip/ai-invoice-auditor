import json
import shutil
import os
from pathlib import Path
from datetime import datetime
from loguru import logger

class InvoiceMonitorAgent:
    # Define supported extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.json', '.md', '.png', '.jpg', '.jpeg'}

    def __init__(self, watch_dir: str = "data/invoices", processed_dir: str = "data/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        
        # Ensure directories exist
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

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
        candidates = []
        for file_path in self.watch_dir.glob("*.*"):
            # Skip hidden, metadata files, and unsupported types
            if (file_path.name.startswith(".") or 
                file_path.suffixes[-2:] == ['.meta', '.json']):
                continue
            
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
                
            candidates.append(file_path)

        # 2. Sort candidates by timestamp (Oldest First - FIFO)
        candidates.sort(key=self._get_sort_key)

        # 3. Build Job Objects
        for file_path in candidates:
            # Load metadata if available
            meta_path = file_path.with_suffix(".meta.json")
            metadata = {}
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"Corrupt metadata for {file_path.name}: {e}")

            jobs.append({
                "file_path": str(file_path),
                "metadata": metadata
            })
            
        return jobs

    def archive(self, file_path_str: str):
        """
        Moves the invoice and its metadata to the 'processed' folder.
        """
        source_path = Path(file_path_str)
        if not source_path.exists():
            logger.warning(f"Cannot archive missing file: {source_path}")
            return

        # 1. Define Destination
        # We append a timestamp to the filename to avoid collisions in the archive
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{timestamp}_{source_path.name}"
        dest_path = self.processed_dir / dest_name

        try:
            # 2. Move Main File
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived file to: {dest_path}")

            # 3. Move Metadata File (if exists)
            meta_source = source_path.with_suffix(".meta.json")
            if meta_source.exists():
                meta_dest = self.processed_dir / f"{timestamp}_{meta_source.name}"
                shutil.move(str(meta_source), str(meta_dest))
                logger.debug(f"Archived metadata to: {meta_dest}")
                
        except Exception as e:
            logger.error(f"Failed to archive {source_path.name}: {e}")