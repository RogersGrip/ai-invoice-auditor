# ===== FILE: src/frameworks/google_adk/types.py =====
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Schema(BaseModel):
    type: str
    properties: Optional[Dict[str, Any]] = None
    required: Optional[List[str]] = None

class FunctionDeclaration(BaseModel):
    name: str
    description: str
    parameters: Optional[Schema] = None

class ToolContext(BaseModel):
    invocation_id: str = Field(default_factory=lambda: "inv-" + str(uuid.uuid4()))
    session_id: Optional[str] = None

class Part(BaseModel):
    text: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    function_response: Optional[Dict[str, Any]] = None

class Content(BaseModel):
    role: str
    parts: List[Part]

import uuid