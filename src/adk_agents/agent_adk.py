# agent_adk.py

import asyncio
import warnings
from typing import Any, Dict, List, Optional, Callable
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.genai.types import Content, Part
from rich.console import Console
from rich.panel import Panel

warnings.filterwarnings('ignore')


class AgentADK:
    """Base class for all ADK agents with improved tool handling"""
    
    def __init__(
        self, 
        name: str, 
        instruction: str, 
        model: str = "bedrock/amazon.nova-lite-v1:0", 
        tools: Optional[List[Callable]] = None,
        enable_memory: bool = False,
        verbose: bool = False
    ):
        """
        Initialize AgentADK
        
        Args:
            name: Agent name
            instruction: Agent instruction/system prompt
            model: LLM model identifier
            tools: List of tool functions (plain Python functions or ADK Tool objects)
            enable_memory: Enable memory service for conversation history
            verbose: Enable verbose console output
        """
        self.console = Console()
        self.name = name
        self.instruction = instruction
        self.tools = tools or []
        self.enable_memory = enable_memory
        self.verbose = verbose
        
        # Validate and prepare tools
        self._prepared_tools = self._prepare_tools()
        
        # Setup agent
        self.agent = Agent(
            model=LiteLlm(model=model),
            name=name,
            instruction=instruction,
            tools=self._prepared_tools
        )
        
        # Setup runner with appropriate services
        self.runner = Runner(
            agent=self.agent,
            session_service=InMemorySessionService(),
            artifact_service=InMemoryArtifactService(),
            memory_service=InMemoryMemoryService() if enable_memory else None,
            app_name=f"{name}_App"
        )
        
        self.session_id = f"{name.replace(' ', '_').lower()}-session-{id(self)}"
        self.user_id = "user-001"
        self._session_initialized = False
    
    def _prepare_tools(self) -> List[Any]:
        """
        Prepare tools for ADK agent.
        Converts plain Python functions to ADK-compatible format if needed.
        
        Returns:
            List of prepared tools
        """
        prepared = []
        for tool in self.tools:
            # If it's already an ADK Tool object, use as-is
            if hasattr(tool, '__class__') and 'Tool' in tool.__class__.__name__:
                prepared.append(tool)
            # If it's a plain function, ADK can handle it directly
            elif callable(tool):
                prepared.append(tool)
            else:
                if self.verbose:
                    self.console.print(f"[yellow]Warning: Unknown tool type: {type(tool)}[/yellow]")
        
        return prepared
    
    async def setup_session(self):
        """Create agent session (idempotent)"""
        if self._session_initialized:
            return
        
        try:
            await self.runner.session_service.create_session(
                app_name=f"{self.name}_App",
                user_id=self.user_id,
                session_id=self.session_id,
                state={}
            )
            self._session_initialized = True
            
            if self.verbose:
                self.console.print(f"[cyan]Session initialized: {self.session_id}[/cyan]")
        except Exception as e:
            if self.verbose:
                self.console.print(f"[yellow]Session setup warning: {e}[/yellow]")
            # Session might already exist, continue anyway
            self._session_initialized = True
    
    async def process_message(self, message: str, return_full_event: bool = False) -> Any:
        """
        Process user message and return response
        
        Args:
            message: User input message
            return_full_event: If True, return full event stream; if False, return text only
            
        Returns:
            Agent response as string or full events
        """
        content = Content(role="user", parts=[Part(text=message)])
        responses = []
        events = []
        
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=self.session_id,
            new_message=content
        ):
            events.append(event)
            
            if event.content:
                for p in event.content.parts:
                    # Extract text content (excluding thoughts)
                    if getattr(p, "text", None) and not getattr(p, "thought", False):
                        responses.append(p.text.strip())
                    
                    # Log tool calls if verbose
                    if self.verbose and hasattr(p, "function_call"):
                        self.console.print(f"[blue]Tool call: {p.function_call}[/blue]")
        
        if return_full_event:
            return events
        
        return "\n".join(responses) if responses else "No response generated"
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.runner.close()
            await asyncio.sleep(0.3)
            self._session_initialized = False
            
            if self.verbose:
                self.console.print("[cyan]Session closed[/cyan]")
        except Exception as e:
            if self.verbose:
                self.console.print(f"[yellow]Cleanup warning: {e}[/yellow]")
    
    async def run(self, message: str, show_panel: bool = True) -> str:
        """
        Main execution flow with automatic session management
        
        Args:
            message: User input message
            show_panel: Display rich panels for output
            
        Returns:
            Agent response as string
        """
        if show_panel:
            self.console.print(Panel(
                f"[bold blue]{self.name}[/bold blue]", 
                border_style="blue"
            ))
            self.console.print(f"\n[dim]Input:[/dim] {message}\n")
        
        await self.setup_session()
        response = await self.process_message(message)
        
        if show_panel:
            self.console.print(Panel(
                f"[bold green]{response}[/bold green]",
                title="Response",
                border_style="green"
            ))
            self.console.print("\n[green]✓ Completed[/green]\n")
        
        await self.cleanup()
        
        return response
    
    def run_sync(self, message: str, show_panel: bool = True) -> str:
        """
        Synchronous wrapper for run()
        
        Args:
            message: User input message
            show_panel: Display rich panels for output
            
        Returns:
            Agent response as string
        """
        return asyncio.run(self.run(message, show_panel))
    
    def print_info(self):
        """Print agent information"""
        self.console.print(f"\n[bold cyan]═══ Agent Info ═══[/bold cyan]")
        self.console.print(f"[cyan]Name:[/cyan] {self.name}")
        self.console.print(f"[cyan]Model:[/cyan] {self.agent.model.__class__.__name__}")
        self.console.print(f"[cyan]Tools:[/cyan] {len(self.tools)}")
        
        if self.tools:
            self.console.print(f"\n[cyan]Available Tools:[/cyan]")
            for i, tool in enumerate(self.tools, 1):
                tool_name = getattr(tool, 'name', getattr(tool, '__name__', 'Unknown'))
                self.console.print(f"  {i}. {tool_name}")
        
        self.console.print(f"[cyan]Memory Enabled:[/cyan] {self.enable_memory}")
        self.console.print(f"[cyan]Session ID:[/cyan] {self.session_id}\n")
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Get conversation history if memory is enabled
        
        Returns:
            List of conversation messages
        """
        if not self.enable_memory:
            return []
        
        # Implementation depends on ADK's memory service API
        # This is a placeholder
        return []