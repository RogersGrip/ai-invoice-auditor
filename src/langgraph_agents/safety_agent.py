import re
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

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
        'email': r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b",
        'phone': r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b",
        'credit_card': r"\b(?:\d[ -]*?){13,16}\b",
        'ssn': r"\b[2-9]{1}[0-9]{3}[-\s]?[0-9]{4}[-\s]?[0-9]{4}\b"
    }

    def __init__(self):
        self.model_id = "cohere.command-r-plus-v1:0"
        try:
            self.llm = ChatBedrockConverse(
                model=self.model_id,
                temperature=0.0,
                max_tokens=1024
            )
        except Exception as e:
            logger.warning(f"Failed to init Bedrock LLM: {e}. Safety checks will run in fallback mode.")
            self.llm = None

    def _redact_pii(self, text: str) -> Tuple[str, List[str]]:
        detected_types = set()
        redacted_text = text
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, redacted_text)
            if matches:
                detected_types.add(pii_type)
                redacted_text = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", redacted_text)
        
        return redacted_text, list(detected_types)

    def _check_toxicity_llm(self, text: str) -> ToxicityAnalysis:
        if not self.llm:
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, reasoning="LLM unavailable")

        prompt = f"""
        Analyze the following invoice text for toxicity, hate speech, and bias.
        Ignore financial terms, names, and addresses unless they are explicitly abusive.
        
        TEXT:
        {text[:2000]}... (truncated)
        
        Return JSON with:
        - toxicity_score (float 0.0-1.0)
        - is_biased (bool)
        - reasoning (string)
        """
        
        try:
            structured_llm = self.llm.with_structured_output(ToxicityAnalysis)
            return structured_llm.invoke([HumanMessage(content=prompt)])
        except Exception as e:
            logger.error(f"Toxicity check failed: {e}")
            return ToxicityAnalysis(toxicity_score=0.0, is_biased=False, reasoning="Check failed")

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        self.start_as_current_observation(inputs)
        
        raw_text = inputs.get("raw_text", "")
        file_name = inputs.get("file_name", "unknown")
        
        if not raw_text:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                source_agent=self.name,
                target_agent="Orchestrator",
                message_type="ERROR",
                payload={"error": "No text to analyze"}
            )

        logger.info(f"Running Safety Checks for {file_name}...")

        # 1. PII Redaction
        redacted_text, pii_found = self._redact_pii(raw_text)
        if pii_found:
            logger.info(f"PII Detected & Redacted: {pii_found}")

        # 2. Toxicity & Bias Check
        analysis = self._check_toxicity_llm(redacted_text)
        
        is_safe = analysis.toxicity_score < 0.8  # Threshold
        
        report = SafetyReport(
            is_safe=is_safe,
            pii_detected=pii_found,
            toxicity_score=analysis.toxicity_score,
            bias_detected=analysis.is_biased,
            details=analysis.reasoning
        )

        return AgentResponse(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source_agent=self.name,
            target_agent="Translation Agent",
            message_type="TASK_HANDOFF",
            payload={
                "safety_report": report.model_dump(),
                "redacted_text": redacted_text,
                "status": "safe" if is_safe else "flagged"
            }
        )