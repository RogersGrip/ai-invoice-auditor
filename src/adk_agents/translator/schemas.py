from pydantic import BaseModel, Field
from typing import Any

class TranslationRequest(BaseModel):
    raw_text: str = Field(..., description="Raw text extracted from the invoice")
    metadata: dict[str, Any] = Field(default_factory=dict, description="File metadata context")
    target_language: str = Field("English", description="Target language")

class TranslationResponse(BaseModel):
    translated_text: str = Field(..., description="Full text translated to English")
    detected_language: str = Field(..., description="The language detected")
    confidence_score: float = Field(..., description="Confidence of translation (0-1)")
    structured_data: dict[str, Any] = Field(..., description="JSON extracted invoice data")