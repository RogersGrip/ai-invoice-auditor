from typing import Dict, Any
import json
from litellm import completion
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from src.core.state import InvoiceData

class TranslatorAgent(Agent):
    name = "Translation Agent"
    description = "Translates and standardizes invoice data to English JSON."

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        raw_text = inputs.get("raw_text")
        if not raw_text:
            return AgentResponse(content=None, metadata={"error": "No text to translate"})

        logger.info("Translator Agent: Standardizing to JSON")
        
        prompt = """
        Extract the following fields from the invoice text and return JSON ONLY:
        - invoice_no (string)
        - invoice_date (YYYY-MM-DD)
        - vendor_id (string)
        - currency (ISO code, e.g. USD, EUR)
        - total_amount (float)
        - line_items (list of objects with: item_code, description, qty, unit_price, total)
        
        Translate any non-English description to English.
        """
        
        try:
            model = settings.TRANSLATION_MODEL
            if settings.MODEL_PROVIDER == "ollama":
                model = f"ollama/{settings.OLLAMA_MODEL}"
            
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": raw_text}
                ]
            )
            
            content_str = response.choices[0].message.content
            # Basic cleanup for Markdown code blocks common in LLM output
            if "```" in content_str:
                content_str = content_str.replace("```json", "").replace("```", "").strip()
            
            # Find the first { and last } to handle chatty introductions
            start_idx = content_str.find("{")
            end_idx = content_str.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content_str = content_str[start_idx:end_idx+1]

            data = json.loads(content_str)
            
            # Validate against Pydantic model
            invoice = InvoiceData(**data)
            
            return AgentResponse(
                content=invoice.model_dump(),
                metadata={"status": "success", "model": model}
            )
            
        except Exception as e:
            logger.error(f"Translation/Extraction Failed: {e}")
            return AgentResponse(content=None, metadata={"error": str(e)})
