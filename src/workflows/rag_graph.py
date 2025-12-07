from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langfuse import observe
from src.langgraph_agents.rag.retriever import RetrievalAgent
from src.langgraph_agents.rag.augmenter import AugmentationAgent
from src.langgraph_agents.rag.generator import GenerationAgent
from src.langgraph_agents.rag.reflector import ReflectionAgent
from src.core.logger import logger

# Define RAG State
class RAGState(TypedDict):
    query: str
    retrieved_docs: List[Dict[str, Any]]
    context: str
    answer: str
    evaluation: Dict[str, Any]

# Initialize Agents
retriever = RetrievalAgent()
augmenter = AugmentationAgent()
generator = GenerationAgent()
reflector = ReflectionAgent()

# Node Functions
@observe(name="retrieve_node")
def retrieve_node(state: RAGState) -> RAGState:
    query = state["query"]
    resp = retriever.process({"query": query, "context_id": "rag_query"})
    # AgentResponse uses payload
    return {"retrieved_docs": resp.payload.get("retrieved_docs")}

@observe(name="augment_node")
def augment_node(state: RAGState) -> RAGState:
    docs = state["retrieved_docs"]
    resp = augmenter.process({"docs": docs, "query": state["query"]}) 
    return {"context": resp.payload.get("context")}

@observe(name="generate_node")
def generate_node(state: RAGState) -> RAGState:
    resp = generator.process({
        "query": state["query"],
        "context": state["context"]
    })
    return {"answer": resp.payload.get("answer")}

@observe(name="reflect_node")
def reflect_node(state: RAGState) -> RAGState:
    resp = reflector.process({
        "query": state["query"],
        "answer": state["answer"],
        "context": state["context"]
    })
    # Payload contains evaluation dict
    return {"evaluation": resp.payload.get("evaluation")}

# Build Graph
def create_rag_graph():
    workflow = StateGraph(RAGState)
    
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("augment", augment_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("reflect", reflect_node)
    
    workflow.set_entry_point("retrieve")
    
    workflow.add_edge("retrieve", "augment")
    workflow.add_edge("augment", "generate")
    workflow.add_edge("generate", "reflect")
    workflow.add_edge("reflect", END)
    
    return workflow.compile()
