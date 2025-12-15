from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
import json
import time
import shutil
from pathlib import Path

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    SAFE = "safe"
    FLAGGED = "flagged"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"
    DATA_INVALID = "data_invalid"
    BUSINESS_MISMATCH = "business_mismatch"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"

class LineItem(BaseModel):
    item_code: Optional[str] = Field(None, description="SKU or Item Code")
    description: Optional[str] = Field(None, description="Description of the line item")
    qty: float = Field(0.0, description="Quantity")
    unit_price: float = Field(0.0, description="Unit price per item")
    currency: str = Field("USD", description="Currency code")
    total: float = Field(0.0, description="Total line amount")

class InvoiceData(BaseModel):
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor_id: Optional[str] = None
    currency: str = "USD"
    total_amount: float = 0.0
    line_items: List[LineItem] = Field(default_factory=list)
    original_language: str = "en"
    translation_confidence: float = 1.0

class SafetyReport(BaseModel):
    is_safe: bool = True
    pii_detected: List[str] = Field(default_factory=list)
    toxicity_score: float = 0.0
    bias_detected: bool = False
    details: str = ""

class ApprovalInfo(BaseModel):
    approved_by: str = "system"
    reason: str = "auto_approved"
    timestamp: str = ""

class InvoiceState(BaseModel):
    file_path: str
    file_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_text: Optional[str] = None
    redacted_text: Optional[str] = None
    safety_report: Optional[SafetyReport] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    standardized_invoice: Optional[InvoiceData] = None
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    report_path: Optional[Dict[str, str]] = None
    current_step: str = "start"
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_log: List[str] = Field(default_factory=list)
    translation_meta: Dict[str, Any] = Field(default_factory=dict)
    approval_info: Optional[ApprovalInfo] = None
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

def update_progress(file_name: str, step: str, status: str = "processing"):
    try:
        project_root = Path.cwd()
        status_path = project_root / "data" / "status.json"
        temp_path = project_root / "data" / "status.tmp"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_file": file_name,
            "step": step,
            "status": status,
            "timestamp": time.time()
        }
        with open(temp_path, "w") as f:
            json.dump(data, f)
        shutil.move(str(temp_path), str(status_path))
    except Exception:
        pass