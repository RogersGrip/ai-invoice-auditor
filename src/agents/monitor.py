import json
from pathlib import Path
from loguru import logger

class InvoiceMonitorAgent:
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.json', '.md'}

    def __init__(self, watch_dir: str = "data/invoices"):
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._processed = set()

    def scan(self) -> list[dict]:
        '''Scan the watch directory for new invoice files

        Args: None

        Returns:
            list[dict]: List of new invoice jobs with file paths and metadata
        '''
        new_jobs = []
        
        for file_path in self.watch_dir.glob("*.*"):
            # 1. Skip hidden files, metadata, and already processed
            if (file_path.name.startswith(".") or 
                file_path.suffixes[-2:] == ['.meta', '.json'] or 
                file_path.name in self._processed):
                continue

            # 2. Skip unsupported extensions
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                if file_path.name not in self._processed:
                    logger.warning(f"Skipping unsupported file format: {file_path.name}")
                    self._processed.add(file_path.name)
                continue

            logger.info(f"New invoice detected: {file_path.name}")
            
            # 3. Load Metadata
            meta_path = file_path.with_suffix(".meta.json")
            metadata = {}
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                    logger.debug(f"Loaded metadata for {file_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to load metadata: {e}")
            
            self._processed.add(file_path.name)
            new_jobs.append({
                "file_path": str(file_path),
                "metadata": metadata
            })
            
        return new_jobs