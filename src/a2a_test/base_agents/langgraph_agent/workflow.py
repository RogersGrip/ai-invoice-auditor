from typing_extensions import TypedDict, Annotated
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from langchain_aws import ChatBedrockConverse
from agent import HelloAgent
import operator

class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    status: str

def agent_node(state: State):
    """Agent node that calls the LLM with tools"""
    model = ChatBedrockConverse(model="amazon.nova-lite-v1:0")
    model_with_tools = model.bind_tools(HelloAgent.tools)
    
    # Build prompt from messages and instructions
    messages = state["messages"]
    prompt = [
        {"role": "system", "content": HelloAgent.SYSTEM_INSTRUCTION + "\n\n" + HelloAgent.FORMAT_INSTRUCTION},
        *messages
    ]
    
    response = model_with_tools.invoke(prompt)
    return {"messages": [response], "status": "initiated"}

def should_continue(state: State):
    """Router to decide next step"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If final response (no tool calls), end
    if not last_message.tool_calls:
        return END
    
    return "tools"

def create_graph():
    """Create LangGraph workflow for HelloAgent"""
    workflow = StateGraph(State)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    tool_node = ToolNode(HelloAgent.tools)
    workflow.add_node("tools", tool_node)
    
    # Edges
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    # Compile with memory
    memory = InMemorySaver()
    graph = workflow.compile(checkpointer=memory)
    
    print(graph.get_graph().draw_ascii())
    return graph
