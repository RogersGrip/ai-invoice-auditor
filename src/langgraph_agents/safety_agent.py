import re
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from src.core.llm_wrapper import BedrockLLMService
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.config import settings
from src.core.state import SafetyReport

class ToxicityAnalysis(BaseModel):
    toxicity_score: float = Field(...)
    is_biased: bool = Field(...)
    pii_leak_risk: bool = Field(...)
    reasoning: str = Field(...)

class SafetyAgent(Agent):
    name = "Safety Agent"
    description = "RAI Guardrail Agent"

    PII_PATTERNS = {
        "EMAIL": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b",
        "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
        "SSN_US": r"\b\d{3}-\d{2}-\d{4}\b",
        "IBAN": r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"
    }

    def __init__(self):
        self.model_id = settings.SAFETY_MODEL
        try:
            self.llm_service = BedrockLLMService(model_id=self.model_id, temperature=0.0)
        except Exception:
            self.llm_service = None

    def _redact_pii(self, text: str) -> Tuple[str, List[str]]:
        detected_types = set()
        redacted_text = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, redacted_text)
            if matches:
                detected_types.add(pii_type)
                redacted_text = re.sub(pattern, f"[{pii_type}_REDACTED]", redacted_text)
        return redacted_text, list(detected_types)

    def _analyze_content_safety(self, text: str) -> ToxicityAnalysis:
        if not self.llm_service:
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, pii_leak_risk=False, reasoning="LLM Unavailable")

        prompt = f"""
        Analyze the following text for Toxicity, Bias, and PII Risks.
        Text: "{text[:3000]}"
        Return valid JSON: {{"toxicity_score": float, "is_biased": bool, "pii_leak_risk": bool, "reasoning": "string"}}
        """
        try:
            response = self.llm_service.invoke(prompt)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return ToxicityAnalysis(**json.loads(match.group(0)))
            raise ValueError("Invalid JSON")
        except Exception as e:
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, pii_leak_risk=False, reasoning=str(e))

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        raw_text = inputs.get("raw_text", "")
        if not raw_text:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Translation Agent",
                message_type="TASK_HANDOFF",
                payload={"safety_report": SafetyReport(is_safe=True).model_dump(), "redacted_text": "", "status": "safe"},
                context_id=inputs.get("context_id")
            )

        redacted_text, pii_found = self._redact_pii(raw_text)
        analysis = self._analyze_content_safety(redacted_text)
        is_safe = (analysis.toxicity_score < 0.7) and (not analysis.is_biased)
        
        report = SafetyReport(
            is_safe=is_safe,
            pii_detected=pii_found,
            toxicity_score=analysis.toxicity_score,
            bias_detected=analysis.is_biased,
            details=analysis.reasoning
        )

        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_agent=self.name,
            target_agent="Translation Agent",
            message_type="TASK_HANDOFF",
            payload={"safety_report": report.model_dump(), "redacted_text": redacted_text, "status": "safe" if is_safe else "flagged"},
            context_id=inputs.get("context_id")
        )