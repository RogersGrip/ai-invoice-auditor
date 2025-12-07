from typing import Literal
from langgraph.graph import StateGraph, END
from src.core.state import InvoiceState, ProcessingStatus
from src.workflows.nodes import (
    extractor_node, 
    translator_node, 
    data_validator_node,
    business_validator_node,
    reporter_node,
    ingestor_node
)

def route_after_extraction(state: InvoiceState) -> Literal["translator", "reporter"]:
    if state.status == ProcessingStatus.FAILED:
        return "reporter"
    return "translator"

def route_after_data_validation(state: InvoiceState) -> Literal["business_validator", "reporter"]:
    # If data is missing critical fields, skip business validation?
    # Or maybe we just report it. 
    # Let's say if data_invalid, we skip business validation to save tokens/resources.
    if state.status == ProcessingStatus.DATA_INVALID:
        return "reporter"
    return "business_validator"

def create_invoice_graph():
    workflow = StateGraph(InvoiceState)

    workflow.add_node("extractor", extractor_node)
    workflow.add_node("translator", translator_node)
    
    # Split Validation Nodes
    workflow.add_node("data_validator", data_validator_node)
    workflow.add_node("business_validator", business_validator_node)
    
    workflow.add_node("reporter", reporter_node)
    workflow.add_node("ingestor", ingestor_node)

    workflow.set_entry_point("extractor")
    
    # Extractor -> Translator (or fail)
    workflow.add_conditional_edges(
        "extractor",
        route_after_extraction,
        {
            "translator": "translator",
            "reporter": "reporter"
        }
    )
    
    # Translator -> Data Validator
    workflow.add_edge("translator", "data_validator")
    
    # Data Validator -> Business Validator (or fail/skip)
    workflow.add_conditional_edges(
        "data_validator",
        route_after_data_validation,
        {
            "business_validator": "business_validator",
            "reporter": "reporter"
        }
    )
    
    workflow.add_edge("business_validator", "reporter")
    workflow.add_edge("reporter", "ingestor")
    workflow.add_edge("ingestor", END)

    return workflow.compile()