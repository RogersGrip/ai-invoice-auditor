from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ToolSignature(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

class AgentCard(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: List[str]
    endpoints: Dict[str, str]
    tools: List[ToolSignature]