from pydantic import BaseModel, Field
from typing import List, Optional

class LineItemExtract(BaseModel):
    item_code: Optional[str] = Field(None, description="SKU, Charge Code, or Item ID")
    description: Optional[str] = Field(None, description="Description of the good or service")
    qty: Optional[float] = Field(None, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price per item")
    currency: Optional[str] = Field(None, description="Currency code (USD, EUR, etc.)")
    total: Optional[float] = Field(None, description="Total line amount")

class InvoiceDataExtract(BaseModel):
    invoice_no: Optional[str] = Field(None, description="Invoice Number")
    invoice_date: Optional[str] = Field(None, description="Date of invoice YYYY-MM-DD")
    vendor_id: Optional[str] = Field(None, description="Vendor Name or ID")
    currency: Optional[str] = Field(None, description="Main currency")
    total_amount: Optional[float] = Field(None, description="Total invoice amount")
    line_items: List[LineItemExtract] = Field(
        default_factory=list, 
        description="All billable items, charges, freight fees, or products lines"
    )


class TranslationRequest(BaseModel):
    raw_text: str = Field(..., description="Raw text extracted from the invoice")
    metadata: dict = Field(default_factory=dict, description="File metadata context")
    target_language: str = Field("English", description="Target language")

class TranslationResponse(BaseModel):
    translated_text: str = Field(..., description="Full text translated to English")
    detected_language: str = Field(..., description="The language detected")
    confidence_score: float = Field(..., description="Confidence of translation (0-1)")
    structured_data: InvoiceDataExtract