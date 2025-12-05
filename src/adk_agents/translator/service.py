import os
import instructor
from litellm import completion
from loguru import logger
from src.adk_agents.translator.schemas import TranslationRequest, TranslationResponse

class TranslatorService:
    def __init__(self):
        self.model = os.getenv("TRANSLATION_MODEL", "bedrock/cohere.command-r-plus-v1:0")
        
        # FIX: Use Mode.MD_JSON to avoid Bedrock parameter conflicts.
        self.client = instructor.from_litellm(
            completion, 
            mode=instructor.Mode.MD_JSON
        )

    def process(self, request: TranslationRequest) -> TranslationResponse:
        logger.info(f"Processing structured translation. Model: {self.model}")
        
        sender = request.metadata.get("sender", "Unknown")
        subject = request.metadata.get("subject", "Invoice")
        
        system_prompt = f"""
        You are an expert Invoice Auditor.
        CONTEXT: Sender: {sender}, Subject: {subject}
        TASK: Detect language, translate to {request.target_language}, and extract data.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this invoice content:\n\n{request.raw_text}"}
                ],
                response_model=TranslationResponse,
                max_tokens=4000,
                temperature=0.0
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Structured Generation Failed: {e}")
            return TranslationResponse(
                translated_text="ERROR",
                detected_language="unknown",
                confidence_score=0.0,
                structured_data={"error": str(e)}
            )