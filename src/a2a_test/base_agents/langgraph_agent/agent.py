import os
from collections.abc import AsyncIterable
from typing import Any, Literal, Dict, Any
import httpx

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from langchain_aws import ChatBedrockConverse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict, Annotated
from pydantic import BaseModel
import operator

memory = InMemorySaver()

# Tools
@tool
def printHello(name: str):
    ''' Greets the user with on the given name '''
    return f"Hello {{{name}}}!"

@tool
def add(a, b):
    ''' Returns the sum '''
    return a + b

# Output Schema
class ResponseSchema(BaseModel):
    ''' Respond to the user in the format '''
    status: Literal['initiated', 'completed', 'error'] = 'initiated'
    result: str

# State Definition
class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    result: str

# Agent
class HelloAgent:
    ''' Hello Agent - Agent that greets and can perform addition for two numbers given '''

    SUPPORTED_TYPES = ["text", "text/plain"]

    SYSTEM_INSTRUCTION = "Specialist in greeting the user and adding two numbers"
    
    FORMAT_INSTRUCTION = (
        "Set the status in response in initiated until the final response is completed\n"
        "Set the status as error if there is error in the processing the request\n"
        "Always respond with a final structured response using the ResponseSchema format."
    )
    
    def __init__(self):
        self.model = ChatBedrockConverse(model="amazon.nova-lite-v1:0")
        self.tools = [printHello, add]
        self.graph = self.create_graph()

    def agent_node(self, state: State) -> Dict[str, Any]:
        """Agent node that calls the LLM with tools"""
        model_with_tools = self.model.bind_tools(self.tools)
        
        messages = state["messages"]
        system_prompt = f"{self.SYSTEM_INSTRUCTION}\n\n{self.FORMAT_INSTRUCTION}"
        
        response = model_with_tools.invoke([
            {"role": "system", "content": system_prompt},
            *messages
        ])
        
        return {
            "messages": [response],
            "status": "initiated"
        }

    def should_continue(self, state: State) -> str:
        """Router to decide next step"""
        last_message = state["messages"][-1]
        if not last_message.tool_calls:
            return END
        return "tools"

    def should_end(self, state: State) -> Dict[str, Any]:
        """Extract final result from last message"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and not last_message.tool_calls:
            return {
                "status": "completed",
                "result": last_message.content
            }
        return {"status": "error", "result": "No final response generated"}

    def create_graph(self):
        """Create LangGraph workflow for HelloAgent"""
        workflow = StateGraph(State)
        
        # Add nodes
        workflow.add_node("agent", self.agent_node)
        tool_node = ToolNode(self.tools)
        workflow.add_node("tools", tool_node)
        workflow.add_node("end", self.should_end)
        
        # Edges
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent", 
            self.should_continue, 
            {"tools": "tools", END: "end"}
        )
        workflow.add_edge("tools", "agent")
        workflow.add_edge("end", END)
        
        # Compile with memory
        graph = workflow.compile(checkpointer=memory)
        return graph

    def invoke(self, input_message: str, context_id: str = None) -> State:
        """Invoke the agent with a message"""
        if context_id is None:
            config = {"configurable": {"thread_id": "test-01"}}
        else:
            config = {"configurable": {"thread_id": context_id}}

        initial_state = {
            "messages": [HumanMessage(content=input_message)],
            "status": "initiated",
            "result": ""
        }
        
        result = self.graph.invoke(initial_state, config)
        return result

    async def ainvoke(self, input_message: str, context_id: str = "test-01") -> State:
        """Async invoke the agent with a message"""
        if config is None:
            config = {"configurable": {"thread_id": context_id}}
        
        initial_state = {
            "messages": [HumanMessage(content=input_message)],
            "status": "initiated",
            "result": ""
        }
        
        result = await self.graph.ainvoke(initial_state, config)
        return result

# Usage example
if __name__ == "__main__":
    agent = HelloAgent()
    
    # Sync invocation
    result = agent.invoke("Hello! Please add 5 + 3")
    print(f"Status: {result['status']}")
    print(f"Result: {result['result']}")
    
    # New conversation
    result2 = agent.invoke("Greet me!")
    print(f"Status: {result2['status']}")
    print(f"Result: {result2['result']}")
