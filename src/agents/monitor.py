from pathlib import Path
from loguru import logger

class InvoiceMonitorAgent:
    def __init__(self, watch_dir: str = "data/invoices"):
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._processed = set()

    def scan(self) -> list[str]:
        new_files = []

        for file_path in self.watch_dir.glob("*.*"):
            if file_path.name not in self._processed and not file_path.name.startswith("."):
                logger.info(f"New invoice detected: {file_path.name}")
                
                self._processed.add(file_path.name)
                new_files.append(str(file_path))
        return new_files