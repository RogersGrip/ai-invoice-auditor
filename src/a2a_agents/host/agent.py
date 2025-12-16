import asyncio
import uuid
from typing import Dict, Any, List
import httpx
from a2a.client import A2ACardResolver
from a2a.types import SendMessageRequest, Message, Role, Part, DataPart
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm  # As per user request: "Make the host agent with LiteLlm()"

from src.a2a_agents.host.remote_agent_connection import RemoteAgentConnections
from src.core.logger import logger
from src.core.protocol import AgentResponse

class HostAgent:
    def __init__(self, name: str = "Host_Agent", model: str = "bedrock/cohere.command-r-plus-v1:0"):
        self.name = name
        self.remote_connections: Dict[str, RemoteAgentConnections] = {}
        
        # Initialize ADK Agent with LiteLLM (CoHere)
        self.agent = Agent(
            model=LiteLlm(model=model),
            name=name,
            instruction="You are a Host Agent. Your job is to orchestrate invoice processing.",
            tools=[]
        )
        self.known_urls = {
            "Extractor Agent": "http://localhost:8001",
            "translation_agent": "http://localhost:8002"
        }

    async def initialize(self):
        """Discover and connect to remote agents"""
        async with httpx.AsyncClient(timeout=10) as client:
            for name, url in self.known_urls.items():
                try:
                    resolver = A2ACardResolver(client, url)
                    card = await resolver.get_agent_card()
                    self.remote_connections[name] = RemoteAgentConnections(card, url)
                    logger.info(f"✅ HostAgent Connected to {name} at {url}")
                except Exception as e:
                    logger.error(f"❌ Failed to connect to {name} at {url}: {e}")

    async def _call_remote_agent(self, agent_name: str, task_text: str, payload: Dict[str, Any] = None) -> Any:
        if agent_name not in self.remote_connections:
            # Try lazy init
            await self.initialize()
            if agent_name not in self.remote_connections:
                 raise Exception(f"Agent {agent_name} not available")

        conn = self.remote_connections[agent_name]
        msg_id, task_id, ctx_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        
        parts = [Part(text=task_text)]
        if payload:
            parts.append(Part(data=DataPart(data=payload)))

        req = SendMessageRequest(
            message=Message(
                messageId=msg_id, role=Role.USER, parts=parts, taskId=task_id, contextId=ctx_id
            )
        )
        
        resp = await conn.send_message(req)
        
        # Extract Result from A2A Response
        # We expect a simple text or data part back
        results = []
        if resp.message and resp.message.parts:
            for p in resp.message.parts:
                if p.data: results.append(p.data.data)
                elif p.text: results.append(p.text)
        
        if not results:
             return None
        return results[0] if len(results) == 1 else results

    async def process_invoice(self, state_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestration Logic:
        1. Call Extractor (Always)
        2. Analyze Language (or check metadata)
        3. Call Translator (If needed)
        4. Aggregate
        """
        logger.info(f"[{self.name}] Processing Invoice...")
        
        # 1. Extraction
        extract_payload = {
            "file_path": state_inputs.get("file_path"),
            "file_name": state_inputs.get("file_name"),
            "metadata": state_inputs.get("metadata", {})
        }
        
        raw_text_result = await self._call_remote_agent("Extractor Agent", "Extract text", extract_payload)
        
        raw_text = ""
        if isinstance(raw_text_result, dict):
            raw_text = raw_text_result.get("raw_text", "")
        elif isinstance(raw_text_result, str):
            raw_text = raw_text_result

        extracted_data = {}
        language = "en"
        
        if raw_text:
            try:
                from langdetect import detect
                language = detect(raw_text)
                logger.info(f"[{self.name}] Detected Language: {language}")
            except:
                pass
        
        if language != "en":
            logger.info(f"[{self.name}] Non-English detected. Calling Translator.")
            trans_result = await self._call_remote_agent("translation_agent", "Translate and Structure", {"raw_text": raw_text})
            if isinstance(trans_result, dict):
                extracted_data = trans_result
        else:
             
             if language == "en":
                 prompt = f"Extract invoice data from this text into JSON: {raw_text[:2000]}..."

                 pass
             else:
                 pass

        
        trans_result = await self._call_remote_agent("translation_agent", "Extract data from this text (Translate if needed)", {"raw_text": raw_text})
        if isinstance(trans_result, dict):
            extracted_data = trans_result

        return {
            "raw_text": raw_text,
            "extracted_data": extracted_data,
            "language": language
        }
