from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from src.agents.rag.retriever import RetrievalAgent
from src.agents.rag.augmenter import AugmentationAgent
from src.agents.rag.generator import GenerationAgent
from src.agents.rag.reflector import ReflectionAgent
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
def retrieve_node(state: RAGState) -> RAGState:
    query = state["query"]
    resp = retriever.process({"query": query})
    return {"retrieved_docs": resp.content}

def augment_node(state: RAGState) -> RAGState:
    docs = state["retrieved_docs"]
    resp = augmenter.process({"docs": docs})
    return {"context": resp.content}

def generate_node(state: RAGState) -> RAGState:
    resp = generator.process({
        "query": state["query"],
        "context": state["context"]
    })
    return {"answer": resp.content}

def reflect_node(state: RAGState) -> RAGState:
    resp = reflector.process({
        "query": state["query"],
        "answer": state["answer"],
        "context": state["context"]
    })
    # Since we removed strict JSON mode, treat content as semi-structured text
    return {"evaluation": {"raw": resp.content}}

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
