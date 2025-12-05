from typing import Literal
from langgraph.graph import StateGraph, END
from src.core.state import InvoiceState, ProcessingStatus
from src.workflows.nodes import (
    extractor_node, 
    translator_node, 
    validator_node, 
    reporter_node
)

def route_after_extraction(state: InvoiceState) -> Literal["translator", "reporter"]:
    """
    Decides next step after extraction.
    If extraction failed, skip to reporting.
    """
    if state['status'] == ProcessingStatus.FAILED:
        return "reporter"
    return "translator"

def route_after_translation(state: InvoiceState) -> Literal["validator", "reporter"]:
    """
    Decides next step after translation.
    If translation/A2A failed, skip to reporting.
    """
    if state['status'] == ProcessingStatus.FAILED:
        return "reporter"
    return "validator"

def create_invoice_graph():
    # 1. Initialize Graph
    workflow = StateGraph(InvoiceState)

    # 2. Add Nodes
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("translator", translator_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("reporter", reporter_node)

    # 3. Define Flow & Conditional Logic
    workflow.set_entry_point("extractor")
    
    # Conditional Edge: Extractor -> (Translator OR Reporter)
    workflow.add_conditional_edges(
        "extractor",
        route_after_extraction,
        {
            "translator": "translator",
            "reporter": "reporter"
        }
    )

    # Conditional Edge: Translator -> (Validator OR Reporter)
    workflow.add_conditional_edges(
        "translator",
        route_after_translation,
        {
            "validator": "validator",
            "reporter": "reporter"
        }
    )

    # Standard Edge: Validator -> Reporter (Validator always reports results)
    workflow.add_edge("validator", "reporter")
    
    # End
    workflow.add_edge("reporter", END)

    return workflow.compile()