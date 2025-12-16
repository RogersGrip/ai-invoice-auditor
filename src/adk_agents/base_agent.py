import asyncio
import os
import warnings
import json
import logging
from typing import List, Any, Dict, Optional, AsyncGenerator

# Concurrency Fix
import nest_asyncio
nest_asyncio.apply()

# LangChain Imports
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import StructuredTool
from pydantic import PrivateAttr, BaseModel, create_model, Field

# Official Google ADK Imports
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.genai.types import Content, Part, Type

from src.core.config import settings
from src.core.logger import logger

warnings.filterwarnings('ignore')

# -------------------------------------------------------------------------
# Types & Helpers
# -------------------------------------------------------------------------
class Event(BaseModel):
    content: Optional[Content] = None

def create_tool_schema(tool: Any) -> Any:
    try:
        decl = tool._get_declaration()
        params = decl.parameters.properties or {}
        required = decl.parameters.required or []
        
        fields = {}
        for name, prop in params.items():
            field_type = str
            if prop.type == Type.NUMBER or prop.type == Type.INTEGER:
                field_type = float
            elif prop.type == Type.BOOLEAN:
                field_type = bool
            elif prop.type == Type.ARRAY:
                field_type = list
            elif prop.type == Type.OBJECT:
                field_type = dict
            
            if name in required:
                fields[name] = (field_type, Field(..., description=prop.description))
            else:
                fields[name] = (Optional[field_type], Field(None, description=prop.description))
        
        return create_model(f"{tool.name.title().replace('_','')}Schema", **fields)
    except Exception as e:
        logger.warning(f"Schema generation failed for {tool.name}: {e}")
        return create_model("FallbackSchema", args=(Dict[str, Any], Field(default_factory=dict)))

# -------------------------------------------------------------------------
# Custom Runner
# -------------------------------------------------------------------------
class CustomRunner:
    def __init__(self, agent, session_service, artifact_service, memory_service, app_name):
        self.agent = agent
        self.session_service = session_service
        self.app_name = app_name

    async def run_async(self, user_id: str, session_id: str, new_message: Content) -> AsyncGenerator[Event, None]:
        logger.info(f"CustomRunner: Processing for {self.agent.name}")
        
        history = [
            Content(role="system", parts=[Part(text=self.agent.instruction)]),
            new_message
        ]
        
        try:
            logger.info("⏳ Calling Bedrock...")
            response = await self.agent.model.generate_response_custom(history)
            
            # Handle Tools
            if response.function_calls:
                logger.info(f"Model requested {len(response.function_calls)} tool calls")
                for fc in response.function_calls:
                    yield Event(content=Content(role="model", parts=[Part(function_call=fc)]))
                    
                    tool_name = fc.get("name")
                    tool_args = fc.get("args", {})
                    
                    logger.info(f"▶️ Executing: {tool_name} {tool_args}")
                    
                    tool = next((t for t in self.agent.tools if t.name == tool_name), None)
                    if tool:
                        try:
                            result = tool.run(tool_args)
                            logger.info(f"✅ Result: {str(result)[:100]}")
                            yield Event(content=Content(role="tool", parts=[Part(
                                function_response={"name": tool_name, "response": result}
                            )]))
                        except Exception as tool_err:
                            logger.error(f"Tool Failed: {tool_err}")
            
            # Yield Text
            if response.text:
                logger.info(f"📄 Response: {response.text[:100]}...")
                yield Event(content=Content(role="model", parts=[Part(text=response.text)]))
                
        except Exception as e:
            logger.error(f"CustomRunner Error: {e}")
            raise e

# -------------------------------------------------------------------------
# Bedrock Adapter
# -------------------------------------------------------------------------
class BedrockADKAdapter(LiteLlm):
    _llm_client: Any = PrivateAttr()
    _bound_client: Any = PrivateAttr()

    def __init__(self, model: str):
        super().__init__(model=model)
        clean_model = model.replace("bedrock/", "").replace("bedrock_converse/", "")
        self._llm_client = ChatBedrockConverse(
            model=clean_model,
            temperature=0.7,
            max_tokens=4096,
            region_name="us-east-1"
        )
        self._bound_client = self._llm_client

    def bind_tools(self, tools: List[Any]):
        lc_tools = []
        for tool in tools:
            schema = create_tool_schema(tool)
            def make_run(t):
                def runner(**kwargs): return t.run(kwargs)
                return runner

            lc_tools.append(StructuredTool.from_function(
                func=make_run(tool),
                name=tool.name,
                description=tool.description,
                args_schema=schema 
            ))
        
        if lc_tools:
            logger.info(f"🔗 Binding {len(lc_tools)} tools")
            self._bound_client = self._llm_client.bind_tools(lc_tools)

    async def generate_response_custom(self, history: List[Content]):
        messages = []
        for c in history:
            text = "\n".join([p.text for p in c.parts if p.text])
            if c.role == "user": messages.append(HumanMessage(content=text))
            elif c.role == "model": messages.append(AIMessage(content=text))
            elif c.role == "system": messages.append(SystemMessage(content=text))
        
        response = await self._bound_client.ainvoke(messages)
        
        text = str(response.content)
        f_calls = []
        if response.tool_calls:
            for tc in response.tool_calls:
                f_calls.append({"name": tc["name"], "args": tc["args"]})
        
        class ResponseObj:
            def __init__(self, t, f):
                self.text = t
                self.function_calls = f
        
        return ResponseObj(text, f_calls)

# -------------------------------------------------------------------------
# Agent Factory
# -------------------------------------------------------------------------
class AgentADK:
    def __init__(self, name: str, instruction: str, model: str = None, tools: list = None):
        self.name = name
        self.instruction = instruction
        self.tools = tools or []
        model_id = f"bedrock/{model or settings.VALIDATION_MODEL}"
        
        self.model_adapter = BedrockADKAdapter(model=model_id)
        self.agent = Agent(
            model=self.model_adapter,
            name=name,
            instruction=instruction,
            tools=self.tools
        )
        self.runner = CustomRunner(
            agent=self.agent,
            session_service=InMemorySessionService(),
            artifact_service=InMemoryArtifactService(),
            memory_service=InMemoryMemoryService(),
            app_name=f"{name}_App"
        )
        self.session_id = f"{name}-session-001"
        self.user_id = "user-001"

    async def setup_session(self): pass

    async def process_message(self, message: str) -> str:
        content = Content(role="user", parts=[Part(text=message)])
        responses = []
        try:
            async for event in self.runner.run_async(self.user_id, self.session_id, content):
                if event.content:
                    for p in event.content.parts:
                        if p.text: responses.append(p.text.strip())
        except Exception as e:
            logger.error(f"Agent Error: {e}")
            return f"Error: {e}"
        return "\n".join(responses)

    async def run(self, message: str) -> str:
        return await self.process_message(message)