import json
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict

# Helper for frontend visualization
def update_progress(file_name: str, step: str, status: str = "processing"):
    try:
        with open("data/status.json", "w") as f:
            json.dump({
                "current_file": file_name,
                "step": step,
                "status": status,
                "timestamp": __import__("time").time()
            }, f)
    except Exception:
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
    validation_results: List[str] = Field(default_factory=list)
    report_path: Optional[Dict[str, str]] = None
    
    current_step: str = "start"
    status: ProcessingStatus = ProcessingStatus.PENDING
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)