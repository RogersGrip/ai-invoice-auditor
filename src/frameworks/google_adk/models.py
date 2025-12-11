# ===== FILE: src/frameworks/google_adk/models.py =====
from typing import List, Any
from src.core.llm_wrapper import BedrockLLMService
from src.core.logger import logger

class LiteLlm:
    """
    Adapter for Bedrock using ChatBedrockConverse, matching the ADK model interface.
    """
    def __init__(self, model: str, aws_access_key_id: str = None, aws_secret_access_key: str = None, aws_region_name: str = None, drop_params: bool = True):
        self.model_name = model.replace("bedrock/", "")
        self.llm_service = BedrockLLMService(model_id=self.model_name, temperature=0.0)
        self.bound_llm = self.llm_service.get_llm()

    def bind_tools(self, tools: List[Any]):
        """
        Binds ADK tools (converted to LangChain format) to the model.
        """
        lc_tools = []
        for tool in tools:
            # Create a dynamic LangChain tool from the ADK tool
            from langchain_core.tools import StructuredTool
            
            def make_run(t):
                def runner(**kwargs):
                    return t.run(kwargs)
                return runner

            lc_tools.append(StructuredTool.from_function(
                func=make_run(tool),
                name=tool.name,
                description=tool.description
            ))
        
        self.bound_llm = self.llm_service.get_llm().bind_tools(lc_tools)

    async def generate_response(self, history: List[Any], tools: List[Any] = []) -> Any:
        """
        Generates a response given the conversation history.
        """
        # Convert ADK Content/Parts to LangChain Messages if needed
        # Assuming history is already a list of LangChain messages or compatible
        try:
            response = await self.bound_llm.ainvoke(history)
            return response
        except Exception as e:
            logger.error(f"LiteLlm Generation Failed: {e}")
            raise e