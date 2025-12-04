import json
from pathlib import Path
from loguru import logger

class InvoiceMonitorAgent:
    def __init__(self, watch_dir: str = "data/invoices"):
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._processed = set()

    def scan(self) -> list[dict]:
        new_jobs = []
        
        # Scan for primary files (PDF, Images)
        for file_path in self.watch_dir.glob("*.*"):
            # Skip hidden files, metadata files themselves, and already processed
            
            if (file_path.name.startswith(".") or 
                # catch .meta.json
                file_path.suffixes[-2:] == ['.meta', '.json'] or 
                file_path.name in self._processed):
                continue

            logger.info(f"New invoice detected: {file_path.name}")
            
            # e.g., invoice.pdf -> invoice.meta.json
            meta_path = file_path.with_suffix(".meta.json")
            metadata = {}
            
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                    logger.debug(f"Loaded metadata for {file_path.name}: {metadata.keys()}")
                except Exception as e:
                    logger.warning(f"Failed to load metadata for {file_path.name}: {e}")
            
            self._processed.add(file_path.name)
            new_jobs.append({
                "file_path": str(file_path),
                "metadata": metadata
            })
            
        return new_jobs