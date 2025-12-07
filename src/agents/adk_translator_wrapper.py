from typing import Dict, Any
from src.core.protocol import Agent, AgentResponse
from src.core.logger import logger
from src.adk_agents.translator.service import TranslatorService
from src.adk_agents.translator.schemas import TranslationRequest

class ADKTranslatorWrapper(Agent):
    name = "ADK Translator Agent"
    description = "Wraps the Google ADK Translator Service for A2A compatibility."

    def __init__(self):
        self.service = TranslatorService()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Adapts the inputs to the ADK service and wraps the output.
        Inputs: 'raw_text'
        """
        raw_text = inputs.get("raw_text")
        # Ensure we have metadata if provided
        metadata = inputs.get("metadata", {})
        
        if not raw_text:
            return AgentResponse(content=None, metadata={"error": "No input text"})

        logger.info("ADK Translator: Standardizing Invoice Data")
        
        try:
            # Construct strict request object
            req = TranslationRequest(
                raw_text=raw_text,
                metadata=metadata,
                target_language="English"
            )
            
            # Call Service
            response = self.service.process(req)
            
            # Valid response is TranslationResponse
            # We want the structured data for the workflow
            extracted_data = response.structured_data.model_dump()
            
            return AgentResponse(
                content=extracted_data,
                metadata={
                    "source": "Google ADK / Instructor",
                    "confidence": response.confidence_score,
                    "language": response.detected_language
                }
            )
            
        except Exception as e:
            logger.error(f"ADK Translation Failed: {e}")
            return AgentResponse(content=None, metadata={"error": str(e)})
