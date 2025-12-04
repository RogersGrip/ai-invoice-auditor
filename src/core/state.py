from enum import Enum
from typing import TypedDict, Any
from pydantic import BaseModel, Field

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"

class LineItem(BaseModel):
    item_code: str | None = Field(None, description="SKU or Item Code")
    description: str | None = None
    qty: float | None = None
    unit_price: float | None = None
    currency: str | None = None
    total: float | None = None

class InvoiceData(BaseModel):
    invoice_no: str | None = None
    invoice_date: str | None = None
    vendor_id: str | None = None
    currency: str | None = None
    total_amount: float | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    original_language: str = "en"
    translation_confidence: float = 1.0

class ValidationResult(BaseModel):
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    discrepancies: list[str] = Field(default_factory=list)

class InvoiceState(TypedDict):
    file_path: str
    file_name: str
    metadata: dict[str, Any]
    raw_text: str | None
    extracted_data: dict[str, Any]
    standardized_invoice: dict[str, Any] | None
    validation_report: dict[str, Any] | None
    current_step: str
    status: ProcessingStatus
    error: str | None