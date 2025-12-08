import sqlite3
from typing import Literal
from langgraph.graph import StateGraph, END
from langfuse import observe

from src.core.state import InvoiceState, ProcessingStatus, update_progress, SafetyReport
from src.core.logger import logger
from src.core.protocol import AgentResponse
from src.core.config import settings

# Agents
from src.langgraph_agents.extractor_agent import ExtractorAgent
from src.langgraph_agents.safety_agent import SafetyAgent
from src.adk_agents.translation_agent import TranslationAgent
from src.adk_agents.validation_agent import DataValidationAgent
from src.adk_agents.business_validator_agent import BusinessValidationAgent
from src.adk_agents.reporting_agent import ReportingAgent
from src.langgraph_agents.rag.indexer import IndexingAgent

extractor = ExtractorAgent()
safety = SafetyAgent()
translator = TranslationAgent()
validator = DataValidationAgent()
biz_validator = BusinessValidationAgent()
reporter = ReportingAgent()
indexer = IndexingAgent()

@observe(name="extraction_node")
def extraction_node(state: InvoiceState) -> InvoiceState:
    update_progress(state.file_name, "Extraction", "Extracting text and data...")
    try:
        resp: AgentResponse = extractor.process({
            "file_path": state.file_path,
            "file_name": state.file_name,
            "metadata": state.metadata
        })
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
        
        state.raw_text = resp.payload.get("raw_text")
        if resp.payload.get("metadata"):
            state.metadata.update(resp.payload.get("metadata"))
        return state
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Extraction Error: {str(e)}")
        return state

@observe(name="safety_node")
def safety_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Safety Check", "Scanning for PII & Toxicity...")
    
    try:
        resp: AgentResponse = safety.process({
            "raw_text": state.raw_text,
            "file_name": state.file_name
        })
        
        payload = resp.payload
        state.redacted_text = payload.get("redacted_text")
        state.safety_report = SafetyReport(**payload.get("safety_report", {}))
        
        if not state.safety_report.is_safe:
            logger.warning(f"Safety Violation in {state.file_name}: {state.safety_report.details}")
            state.status = ProcessingStatus.FLAGGED
        
        return state
    except Exception as e:
        logger.error(f"Safety Check Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Safety Error: {str(e)}")
        return state

@observe(name="translation_node")
def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    
    # Use redacted text if available
    text_to_process = state.redacted_text if state.redacted_text else state.raw_text
    
    update_progress(state.file_name, "Translation", "Standardizing to JSON...")
    try:
        resp: AgentResponse = translator.process({
            "raw_text": text_to_process,
            "file_name": state.file_name
        })
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
            
        state.extracted_data = resp.payload.get("extracted_data")
        state.translation_meta = {"model": resp.payload.get("model")}
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
            "file_name": state.file_name
        })
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
        resp: AgentResponse = biz_validator.process({
            "extracted_data": state.extracted_data,
            "file_name": state.file_name
        })
        payload = resp.payload
        state.validation_results["business_status"] = payload.get("business_validation_status")
        state.validation_results["discrepancies"] = payload.get("discrepancies", [])
        
        if payload.get("discrepancies") or not state.validation_results.get("is_valid"):
            state.validation_results["is_valid"] = False
            
        return state
    except Exception as e:
        logger.error(f"Business Validation Failed: {e}")
        state.error_log.append(f"Business Validation Warning: {str(e)}")
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
            "validation_results": state.validation_results,
            "safety_report": state.safety_report.model_dump() if state.safety_report else None,
            "status": state.status,
            "metadata": state.metadata,
            "file_path": state.file_path
        })
        
        if state.status != ProcessingStatus.FLAGGED:
            state.status = ProcessingStatus.COMPLETED
            
        state.report_path = resp.payload
        return state
    except Exception as e:
        logger.error(f"Reporting Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Reporting Error: {str(e)}")
        return state

@observe(name="ingestion_node")
def ingestion_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Ingestion", "Indexing to Vector DB...")
    try:
        text_content = state.redacted_text or state.raw_text or ""
        struct_data = f"\n[STRUCTURED_DATA]\n{state.extracted_data}"
        
        indexer.process({
            "text": text_content + struct_data,
            "filename": state.file_name,
            "metadata": state.metadata
        })
    except Exception as e:
        logger.warning(f"Ingestion Failed (Non-blocking): {e}")
    
    final_msg = "Completed." if state.status == ProcessingStatus.COMPLETED else "Completed with Flags."
    update_progress(state.file_name, "Completed", final_msg)
    return state

def route_after_extraction(state: InvoiceState) -> Literal["safety", "reporting"]:
    if state.status == ProcessingStatus.FAILED:
        return "reporting"
    return "safety"

def route_after_safety(state: InvoiceState) -> Literal["translation", "reporting"]:
    # Even if flagged, we might want to report it immediately or continue cautiously
    # For this sprint: if unsafe, we go to reporting to generate the 'Flagged' report
    if state.status == ProcessingStatus.FLAGGED:
        return "reporting"
    if state.status == ProcessingStatus.FAILED:
        return "reporting"
    return "translation"

def create_invoice_graph():
    workflow = StateGraph(InvoiceState)
    
    workflow.add_node("extraction", extraction_node)
    workflow.add_node("safety", safety_node)
    workflow.add_node("translation", translation_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("business_validation", business_validation_node)
    workflow.add_node("reporting", reporting_node)
    workflow.add_node("ingestion", ingestion_node)
    
    workflow.set_entry_point("extraction")
    
    workflow.add_conditional_edges(
        "extraction",
        route_after_extraction,
        {"safety": "safety", "reporting": "reporting"}
    )
    
    workflow.add_conditional_edges(
        "safety",
        route_after_safety,
        {"translation": "translation", "reporting": "reporting"}
    )
    
    workflow.add_edge("translation", "validation")
    workflow.add_edge("validation", "business_validation")
    workflow.add_edge("business_validation", "reporting")
    workflow.add_edge("reporting", "ingestion")
    workflow.add_edge("ingestion", END)
    
    # Checkpointer Setup
    from langgraph.checkpoint.sqlite import SqliteSaver
    db_path = str(settings.DATA_DIR / "checkpoints.sqlite")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    
    return workflow.compile(checkpointer=checkpointer)