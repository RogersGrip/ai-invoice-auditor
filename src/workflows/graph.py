from typing import TypedDict, List, Dict, Any, Union, Literal
from langgraph.graph import StateGraph, END
from langfuse import observe
from src.core.state import InvoiceState, ProcessingStatus, update_progress
from src.core.logger import logger
from src.core.protocol import AgentResponse

# Import Agents (New Structure)
from src.langgraph_agents.extractor_agent import ExtractorAgent
from src.langgraph_agents.translation_agent import TranslatorAgent
from src.langgraph_agents.validation_agent import DataValidationAgent
from src.adk_agents.business_validator_agent import BusinessValidationAgent
from src.langgraph_agents.reporting_agent import ReporterAgent
from src.langgraph_agents.rag.indexer import IndexingAgent

# Initialize Agents
extractor = ExtractorAgent()
translator = TranslatorAgent()
validator = DataValidationAgent()
biz_validator = BusinessValidationAgent()
reporter = ReporterAgent()
indexer = IndexingAgent()

# --- Node Functions ---
# Each node wraps an agent's process() method and maps A2A response to State

@observe(name="extraction_node")
def extraction_node(state: InvoiceState) -> InvoiceState:
    update_progress(state.file_name, "Extraction", "Extracting text and data...")
    try:
        # A2A Protocol: Call process with inputs dict
        resp: AgentResponse = extractor.process({
            "file_path": state.file_path, 
            "context_id": state.file_name,
            "metadata": state.metadata
        })
        
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
            
        payload = resp.payload
        # Depending on AgentResponse payload structure from ExtractorAgent
        state.raw_text = payload.get("raw_text")
        # Metadata merge
        if payload.get("metadata"):
            state.metadata.update(payload.get("metadata"))
        
        return state
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Extraction Error: {str(e)}")
        return state

@observe(name="translation_node")
def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Translation", "Standardizing to JSON...")
    
    try:
        resp: AgentResponse = translator.process({
            "raw_text": state.raw_text,
            "context_id": state.file_name
        })
        
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
            
        payload = resp.payload
        # Translator returns 'extracted_data' (dict) and 'english_text' etc
        state.extracted_data = payload.get("extracted_data")
        state.translation_meta = {"model": payload.get("model")}
        
        return state
    except Exception as e:
        logger.error(f"Translation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Translation Error: {str(e)}")
        return state

@observe(name="validation_node")
def validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Validation", "Checking completeness...")
    
    try:
        resp: AgentResponse = validator.process({
            "extracted_data": state.extracted_data,
            "context_id": state.file_name
        })
        
        if resp.message_type == "ERROR":
             raise Exception(resp.payload.get("error"))

        payload = resp.payload
        state.validation_results = {
            "is_valid": payload.get("validation_status") == "valid",
            "missing_fields": payload.get("missing_fields", [])
        }
        
        return state
    except Exception as e:
        logger.error(f"Validation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Validation Error: {str(e)}")
        return state

@observe(name="business_validation_node")
def business_validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Business Validation", "Cross-referencing with ERP...")
    
    try:
        # Note: Business Validator expects 'extracted_data' in inputs or payload
        # And it returns 'validated_data', 'business_validation_status', 'discrepancies'
        resp: AgentResponse = biz_validator.process({
            "extracted_data": state.extracted_data,
            "context_id": state.file_name
        })
        
        if resp.message_type == "ERROR":
             raise Exception(resp.payload.get("error"))

        payload = resp.payload
        state.extracted_data = payload.get("validated_data", state.extracted_data) # Might be enriched
        
        # Merge business status into validation_results
        state.validation_results["business_status"] = payload.get("business_validation_status")
        state.validation_results["discrepancies"] = payload.get("discrepancies", [])
        
        # Consolidate Logic for overall validity
        if payload.get("discrepancies") or not state.validation_results.get("is_valid"):
             state.validation_results["is_valid"] = False
        # If it was valid before and no discrepancies, it remains valid (True)
             
        return state
    except Exception as e:
        logger.error(f"Business Validation Failed: {e}")
        state.error_log.append(f"Business Validation Warning/Error: {str(e)}")
        state.validation_results["business_status"] = "error"
        return state

@observe(name="reporting_node")
def reporting_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Reporting", "Generating reports...")
    
    try:
        resp: AgentResponse = reporter.process({
            "file_name": state.file_name,
            "extracted_data": state.extracted_data,
            "validation_report": state.validation_results,
            "overall_status": state.status, # Should be PENDING/PROCESSING still
            "metadata": state.metadata,
            "file_path": state.file_path,
            "context_id": state.file_name
        })
        
        if resp.message_type == "ERROR":
             raise Exception(resp.payload.get("error"))
             
        # Done
        state.status = ProcessingStatus.COMPLETED
        return state
        
    except Exception as e:
        logger.error(f"Reporting Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Reporting Error: {str(e)}")
        return state

@observe(name="ingestion_node")
def ingestion_node(state: InvoiceState) -> InvoiceState:
    # Optional Side Effect: Verify if Indexing is needed here or implicitly handled
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Ingestion", "Indexing to Vector DB...")
    
    try:
        if state.raw_text:
            resp: AgentResponse = indexer.process({
                "text": state.raw_text,
                "filename": state.file_name,
                "metadata": state.metadata,
                "context_id": state.file_name
            })
            
    except Exception as e:
        logger.warning(f"Ingestion Failed (Non-blocking): {e}")
        
    # Finalize Progress
    update_progress(state.file_name, "Completed", "Processed successfully.")
    return state

# --- Conditionals ---

def route_after_extraction(state: InvoiceState) -> Literal["translation", "reporting"]:
    if state.status == ProcessingStatus.FAILED:
        return "reporting"
    return "translation"

def route_after_data_validation(state: InvoiceState) -> Literal["business_validation", "reporting"]:
    # If basic validation fails, we might still want business validation or skip it?
    # Logic: If invalid structure, business validation might crash.
    if not state.validation_results.get("is_valid"):
        # For now, let's skip business validation if data is missing critical fields
        # But we still want reporting
        # AGENTS.md workflow implies sequential.
        # Let's try to proceed unless critical failure.
        pass
    return "business_validation"

# --- Graph Definition ---
def create_invoice_graph():
    workflow = StateGraph(InvoiceState)
    
    workflow.add_node("extraction", extraction_node)
    workflow.add_node("translation", translation_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("business_validation", business_validation_node)
    workflow.add_node("reporting", reporting_node)
    workflow.add_node("ingestion", ingestion_node)
    
    workflow.set_entry_point("extraction")
    
    workflow.add_conditional_edges(
        "extraction",
        route_after_extraction,
        {
            "translation": "translation",
            "reporting": "reporting" # If failed, go straight to report (generating error report if implemented)
        }
    )
    
    workflow.add_edge("translation", "validation")
    workflow.add_edge("validation", "business_validation")
    workflow.add_edge("business_validation", "reporting")
    
    # Ingestion after reporting
    workflow.add_edge("reporting", "ingestion")
    workflow.add_edge("ingestion", END)
    
    return workflow.compile()