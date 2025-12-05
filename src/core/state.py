from enum import Enum
from typing import List, Dict, Any, TypedDict
from pydantic import BaseModel, Field

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"

class LineItem(BaseModel):
    item_code: str = Field(..., description="SKU or Item Code")
    description: str | None = None
    qty: float = 0.0
    unit_price: float = 0.0
    currency: str = "USD"
    total: float = 0.0

class InvoiceData(BaseModel):
    invoice_no: str | None = None
    invoice_date: str | None = None
    vendor_id: str | None = None
    currency: str = "USD"
    total_amount: float = 0.0
    line_items: List[LineItem] = Field(default_factory=list)
    original_language: str = "en"
    translation_confidence: float = 1.0

class ValidationDiscrepancy(BaseModel):
    item_code: str
    reason: str
    severity: str = "medium"

class ValidationReport(BaseModel):
    is_valid: bool = False
    missing_fields: List[str] = Field(default_factory=list)
    discrepancies: List[ValidationDiscrepancy] = Field(default_factory=list)
    total_lines_processed: int = 0
    auto_approval_eligible: bool = False

class InvoiceState(TypedDict):
    job_id: str
    file_path: str
    file_name: str
    file_metadata: Dict[str, Any]
    raw_text: str | None
    extracted_data: Dict[str, Any]
    standardized_invoice: InvoiceData | None
    validation_report: ValidationReport | None
    current_step: str
    status: ProcessingStatus
    error_log: List[str]