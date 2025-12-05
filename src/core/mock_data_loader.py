import json
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger
from src.core.logger import find_project_root

class MockDataLoader:
    """Loader for mock data files used in testing and validation."""
    def __init__(self):
        # Ascend to project root from: src/core/mock_data_loader.py
        self.project_root = find_project_root(Path(__file__).resolve())
        
        # Point to your specific mock data folder
        self.data_dir = self.project_root / "mock_records" / "validation_data"
        
    def load_po_records(self) -> List[Dict[str, Any]]:
        # User specified filename: PO_Records.json
        return self._load_json("PO_Records.json")

    def load_sku_master(self) -> List[Dict[str, Any]]:
        # User specified filename: sku_master.json
        return self._load_json("sku_master.json")

    def load_vendors(self) -> List[Dict[str, Any]]:
        # Assuming vendors.json might be there or in the future
        try:
            return self._load_json("vendors.json")
        except FileNotFoundError:
            return []

    def _load_json(self, filename: str) -> Any:
        file_path = self.data_dir / filename
        
        if not file_path.exists():
            logger.error(f"Mock Data file missing: {file_path}")
            raise FileNotFoundError(f"Mock data file not found: {file_path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(f"Loaded {len(data)} records from {filename}")
            return data

# Global instance for import
mock_db = MockDataLoader()