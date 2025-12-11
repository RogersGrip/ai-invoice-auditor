# ===== FILE: src/adk_agents/base_adk.py =====
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from src.core.protocol import Agent
from src.core.llm_wrapper import BedrockLLMService
from src.core.logger import logger

class ADKAgent(Agent):
    def __init__(self, name: str, description: str, model_id: str = None):
        self._name = name
        self._description = description
        self.llm_service = BedrockLLMService(model_id=model_id)
        self.tools_map = {}
        self.llm_with_tools = None

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description

    def register_tools(self, tools: List[Any]):
        self.tools_map = {t.name: t for t in tools}
        self.llm_with_tools = self.llm_service.bind_tools(tools)

    def _execute_tool(self, tool_name: str, args: Dict) -> Any:
        if tool_name not in self.tools_map:
            return f"Error: Tool {tool_name} not found."
        try:
            logger.info(f"[{self.name}] 🛠️ LLM Calling Tool: {tool_name} | Args: {args}")
            tool_instance = self.tools_map[tool_name]
            
            # FIX: Use .invoke() for LangChain tools (StructuredTool) instead of .run(**args)
            # .invoke(args) correctly routes the dictionary to the tool's input schema
            if hasattr(tool_instance, "invoke"):
                return tool_instance.invoke(args)
            elif hasattr(tool_instance, "run"):
                # Fallback: Pass args as the single positional 'tool_input' argument
                return tool_instance.run(args)
            elif callable(tool_instance):
                return tool_instance(**args)
            return "Error: Tool not callable."
        except Exception as e:
            logger.error(f"Tool Execution Failed: {e}")
            return f"Tool Error: {str(e)}"

    def run_loop(self, user_input: str, context: Dict[str, Any] = {}) -> Dict[str, Any]:
        messages = [
            SystemMessage(content=f"You are the {self.name}. {self.description}. Use tools when necessary."),
            HumanMessage(content=f"Context: {context}\n\nTask: {user_input}")
        ]
        
        # Limit turns to prevent infinite loops
        for i in range(5):
            try:
                response = self.llm_with_tools.invoke(messages)
                messages.append(response)

                if not response.tool_calls:
                    return {"output": response.content, "status": "completed"}

                for tool_call in response.tool_calls:
                    t_result = self._execute_tool(tool_call["name"], tool_call["args"])
                    
                    messages.append(ToolMessage(
                        tool_call_id=tool_call["id"],
                        name=tool_call["name"],
                        content=str(t_result)
                    ))
            except Exception as e:
                logger.error(f"Agent Loop Error at turn {i}: {e}")
                return {"output": str(e), "status": "failed"}
        
        return {"output": messages[-1].content, "status": "max_turns_reached"}