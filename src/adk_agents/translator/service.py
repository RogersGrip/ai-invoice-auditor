import os
import instructor
from litellm import completion
from langdetect import detect, LangDetectException
from loguru import logger
from src.adk_agents.translator.schemas import TranslationRequest, TranslationResponse

class TranslatorService:
    def __init__(self):
        self.model = os.getenv("TRANSLATION_MODEL", "bedrock/cohere.command-r-plus-v1:0")
        self.client = instructor.from_litellm(
            completion,
            mode=instructor.Mode.MD_JSON
        )

    def _detect_language(self, text: str, metadata: dict) -> str:
        # Layer 1: Metadata Trust
        if metadata and metadata.get("language"):
            lang = metadata["language"].lower()
            logger.debug(f"Language detected via Metadata: {lang}")
            return lang
        
        # Layer 2: Heuristics (langdetect)
        try:
            lang = detect(text)
            logger.debug(f"Language detected via Heuristics: {lang}")
            return lang
        except LangDetectException:
            logger.warning("Heuristic language detection failed.")
        
        # Layer 3: Fallback to LLM (Handled in prompt)
        return "unknown"

    def process(self, request: TranslationRequest) -> TranslationResponse:
        logger.info(f"Processing structured translation/standardization. Model: {self.model}")
        
        detected_lang = self._detect_language(request.raw_text[:1000], request.metadata)
        
        # Dynamic Prompt Selection
        if detected_lang == 'en' or detected_lang == 'english':
            system_prompt = """
            You are an expert Data Extraction Specialist.
            TASK: Extract structured data from this English invoice.
            Do NOT translate. Strictly map the text to the JSON schema.
            """
        else:
            system_prompt = f"""
            You are an expert Invoice Auditor.
            TASK:
            1. Translate content to {request.target_language}.
            2. Extract structured data from the translated text.
            """

        sender = request.metadata.get("sender", "Unknown")
        subject = request.metadata.get("subject", "Invoice")
        
        context_prompt = f"CONTEXT: Sender: {sender}, Subject: {subject}\n\n{system_prompt}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": context_prompt},
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
                structured_data={"invoice_no": None, "line_items": []} # Return empty valid structure on fail
            )