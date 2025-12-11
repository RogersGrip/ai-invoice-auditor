import re
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from src.core.llm_wrapper import BedrockLLMService
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.core.config import settings
from src.core.state import SafetyReport

class ToxicityAnalysis(BaseModel):
    toxicity_score: float = Field(..., description="Score from 0.0 to 1.0 (1.0 is highly toxic)")
    is_biased: bool = Field(..., description="True if bias is detected")
    reasoning: str = Field(..., description="Explanation of findings")

class SafetyAgent(Agent):
    name = "Safety Agent"
    description = "Scans text for PII, Toxicity, and Bias using Regex and LLM guardrails."
    
    PII_PATTERNS = {
        "EMAIL": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b",
        "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
        "SSN": r"\b[2-9]{1}[0-9]{3}[-\s]?[0-9]{4}[-\s]?[0-9]{4}\b"
    }

    def __init__(self):
        self.model_id = settings.SAFETY_MODEL
        try:
            # Replaced BedrockCommandRPlus with BedrockLLMService
            self.llm_service = BedrockLLMService(
                model_id=self.model_id,
                temperature=0.0
            )
        except Exception as e:
            logger.warning(f"Failed to init Bedrock LLM: {e}. Safety checks will run in fallback mode.")
            self.llm_service = None

    def _redact_pii(self, text: str) -> tuple[str, List[str]]:
        detected_types = set()
        redacted_text = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, redacted_text)
            if matches:
                detected_types.add(pii_type)
                redacted_text = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", redacted_text)
        return redacted_text, list(detected_types)

    def _check_toxicity_llm(self, text: str) -> ToxicityAnalysis:
        if not self.llm_service:
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, reasoning="LLM unavailable")
        
        prompt = f"""
        Analyze the text below for toxicity, hate speech, and bias.
        Return a valid JSON object with:
        - "toxicity_score": float (0.0 = safe, 1.0 = toxic)
        - "is_biased": boolean
        - "reasoning": string (brief explanation)
        
        Text to analyze:
        {text[:2000]}...
        
        JSON OUTPUT:
        """
        try:
            # Use the new invoke method
            content = self.llm_service.invoke(prompt)
            content = content.strip()
            
            # Extract JSON from potential markdown blocks
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                json_str = match.group(0)
                data = json.loads(json_str)
                return ToxicityAnalysis(**data)
            else:
                score = 0.8 if "toxic" in content.lower() else 0.0
                return ToxicityAnalysis(toxicity_score=score, is_biased=False, reasoning="Parse Error, manual fallback")
        except Exception as e:
            logger.warning(f"Toxicity check failed: {e}")
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, reasoning="Safety Check Skipped (Error)")

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        raw_text = inputs.get("raw_text", "")
        file_name = inputs.get("file_name", "unknown")
        
        if not raw_text:
            report = SafetyReport(is_safe=True, details="No text content.")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent=self.name,
                target_agent="Translation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "safety_report": report.model_dump(),
                    "redacted_text": "",
                    "status": "safe"
                },
                context_id=inputs.get("context_id")
            )

        logger.info(f"Running Safety Checks for {file_name}...")
        redacted_text, pii_found = self._redact_pii(raw_text)
        
        if pii_found:
            logger.info(f"PII Detected & Redacted: {pii_found}")
            
        analysis = self._check_toxicity_llm(redacted_text)
        is_safe = analysis.toxicity_score < 0.8

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
            payload={
                "safety_report": report.model_dump(),
                "redacted_text": redacted_text,
                "status": "safe" if is_safe else "flagged"
            },
            context_id=inputs.get("context_id")
        )