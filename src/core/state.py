import json
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict

# Helper for frontend visualization
def update_progress(file_name: str, step: str, status: str = "processing"):
    from pathlib import Path
    import time
    import shutil
    
    # Use absolute path relative to project root
    # Use CWD (Safe since we run from run.ps1 in root)
    try:
        project_root = Path.cwd()
        status_path = project_root / "data" / "status.json"
        
        # fallback if CWD is wrong (e.g. inside src?)
        if not (project_root / "run.ps1").exists():
             # Fallback to file traversal if not in root
             project_root = Path(__file__).resolve().parent.parent.parent
             status_path = project_root / "data" / "status.json"

        temp_path = project_root / "data" / "status.tmp"
        
        status_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "current_file": file_name,
            "step": step,
            "status": status,
            "timestamp": time.time()
        }
        
        # Retry logic for Windows file locking
        for attempt in range(3):
            try:
                # Write to temp file first (Atomic Write Pattern)
                with open(temp_path, "w") as f:
                    json.dump(data, f)
                
                # Rename temp to actual (Atomic on POSIX, reduced risk on Windows)
                shutil.move(str(temp_path), str(status_path))
                break
            except Exception:
                time.sleep(0.1 * (attempt + 1))
                
    except Exception as e:
        print(f"DEBUG: Status Update Critical Fail: {e}")
        pass

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"
    DATA_INVALID = "data_invalid"
    FLAGGED = "flagged"

class LineItem(BaseModel):
    item_code: Optional[str] = Field(None, description="SKU or Item Code")
    description: Optional[str] = None
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    currency: Optional[str] = None
    total: Optional[float] = None

class InvoiceData(BaseModel):
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor_id: Optional[str] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    line_items: List[LineItem] = Field(default_factory=list)
    original_language: str = "en"
    translation_confidence: float = 1.0

class ValidationResult(BaseModel):
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    discrepancies: List[str] = Field(default_factory=list)
    total_lines: int = 0

class InvoiceState(BaseModel):
    """
    Global Core State for the Invoice Processing Workflow.
    Replacing TypedDict with strict Pydantic Model.
    """
    file_path: str
    file_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    raw_text: Optional[str] = None
    
    # Structured Data
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    standardized_invoice: Optional[InvoiceData] = None
    
    # Reports
    validation_report: Optional[ValidationResult] = None
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    report_path: Optional[Dict[str, str]] = None
    
    current_step: str = "start"
    status: ProcessingStatus = ProcessingStatus.PENDING
    error: Optional[str] = None
    error_log: List[str] = Field(default_factory=list)
    translation_meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)