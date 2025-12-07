from typing import Dict, Any
import json
import uuid
from datetime import datetime
from litellm import completion
from src.core.protocol import Agent, AgentResponse
from src.core.config import settings
from src.core.logger import logger
from src.core.state import InvoiceData
from src.tools.tools import LangBridgeTool

class TranslatorAgent(Agent):
    name = "Translation Agent"
    description = "Translates and standardizes invoice data to English JSON using LangBridge."

    def __init__(self):
        self.bridge_tool = LangBridgeTool()

    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        # Resolve Input
        raw_text = inputs.get("raw_text")
        if not raw_text and inputs.get("payload"):
            raw_text = inputs["payload"].get("raw_text")

        if not raw_text:
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": "No text to translate"},
                 context_id=inputs.get("context_id")
            )

        logger.info("Translator Agent: Standardizing to JSON")
        
        # In a real scenario, the LangBridgeTool.run() would handle the LLM call.
        # But LangBridgeTool defined in tools.py is currently empty/mock or simple wrapper.
        # AGENTS.md says Tools: Lang-Bridge Tool (LLM Translation).
        # We should keep the logic here OR move it to the tool. 
        # Refactoring logic into the tool would be cleaner but higher risk of breaking something if not careful.
        # Recommendation: Use existing logic but wrapped/referenced as the tool's action.
        
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
                ],
                format="json"
            )
            
            content_str = response.choices[0].message.content
            
            # Robust JSON cleaning
            import re
            
            # Try to find JSON block
            match = re.search(r"\{.*\}", content_str, re.DOTALL)
            if match:
                content_str = match.group(0)
            
            # Clean up potential markdown or comments
            if "```" in content_str:
                content_str = re.sub(r"```\w*", "", content_str).replace("```", "")
            
            content_str = content_str.strip()
            
            # Attempt load
            try:
                data = json.loads(content_str)
            except json.JSONDecodeError:
                # Fallback: simple cleanup of keys
                # This is risky but helps with "property name enclosed in double quotes" if keys are single quoted
                # Replaces single quotes around keys with double quotes
                 content_str = re.sub(r"\'(\w+)\'\s*:", r'"\1":', content_str)
                 data = json.loads(content_str)
                 
            invoice = InvoiceData(**data)
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now().isoformat(),
                source_agent=self.name,
                target_agent="Data Validation Agent",
                message_type="TASK_HANDOFF",
                payload={
                    "extracted_data": invoice.model_dump(),
                    "english_text": "Extracted JSON", # Placeholder
                    "model": model
                },
                context_id=inputs.get("context_id")
            )
            
        except Exception as e:
            logger.error(f"Translation/Extraction Failed: {e}")
            return AgentResponse(
                 id=str(uuid.uuid4()),
                 source_agent=self.name,
                 timestamp=datetime.now().isoformat(),
                 target_agent="Error Handler",
                 message_type="ERROR",
                 payload={"error": str(e)},
                 context_id=inputs.get("context_id")
            )
