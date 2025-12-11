# ===== FILE: src/frameworks/google_adk.py =====
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Callable
import uuid
from src.core.protocol import AgentResponse
from src.core.logger import logger
from src.core.llm_wrapper import BedrockLLMService  # Using Bedrock as the underlying engine for consistency

class ADKContext:
    """
    Represents the context passed between agents in the Google ADK framework.
    """
    def __init__(self, context_id: str, payload: Dict[str, Any]):
        self.context_id = context_id
        self.payload = payload
        self.history: List[str] = []

    def add_history(self, event: str):
        self.history.append(event)

class ADKTool:
    """
    Base class for tools compatible with Google ADK agents.
    """
    def __init__(self, name: str, func: Callable, description: str):
        self.name = name
        self.func = func
        self.description = description

    def execute(self, **kwargs):
        return self.func(**kwargs)

class ADKAgent(ABC):
    """
    Base Agent class following the Google ADK architecture.
    """
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.tools: Dict[str, ADKTool] = {}
        self.llm = BedrockLLMService(temperature=0.0)

    def add_tool(self, tool: ADKTool):
        self.tools[tool.name] = tool

    @abstractmethod
    def observe(self, context: ADKContext) -> ADKContext:
        """
        The 'Observe' phase: Gather information.
        """
        pass

    @abstractmethod
    def think(self, context: ADKContext) -> ADKContext:
        """
        The 'Think' phase: Decide what to do (ReAct pattern).
        """
        pass

    @abstractmethod
    def act(self, context: ADKContext) -> AgentResponse:
        """
        The 'Act' phase: Execute tools and return the final response.
        """
        pass

    def run(self, inputs: Dict[str, Any]) -> AgentResponse:
        """
        Standard execution pipeline for ADK agents.
        """
        context_id = inputs.get("context_id", str(uuid.uuid4()))
        context = ADKContext(context_id, inputs)
        
        logger.info(f"[{self.name}] (Google ADK) Started. Context ID: {context_id}")
        
        # 1. Observe
        context = self.observe(context)
        
        # 2. Think
        context = self.think(context)
        
        # 3. Act
        response = self.act(context)
        
        logger.info(f"[{self.name}] (Google ADK) Finished.")
        return response