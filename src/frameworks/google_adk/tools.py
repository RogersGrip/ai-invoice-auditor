# ===== FILE: src/frameworks/google_adk/tools.py =====
from abc import ABC
from typing import Dict, Any
from src.frameworks.google_adk.types import FunctionDeclaration, ToolContext, Schema

class BaseTool(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def _get_declaration(self) -> FunctionDeclaration:
        """
        Default declaration generation. Can be overridden.
        """
        # Simple schema inference for demonstration if not overridden
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=Schema(type="OBJECT", properties={}, required=[])
        )

    async def run_async(self, args: Dict[str, Any], ctx: ToolContext) -> Any:
        """
        Async execution handler.
        """
        return self.run(args)

    def run(self, args: Dict[str, Any]) -> Any:
        """
        Sync execution handler.
        """
        raise NotImplementedError("Tool must implement run or run_async")