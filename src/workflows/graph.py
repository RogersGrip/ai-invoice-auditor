import shutil
import json
from typing import Literal, Dict, Any
from pathlib import Path
from langgraph.graph import StateGraph, END
from langfuse import observe
from langgraph.checkpoint.memory import MemorySaver

from src.core.state import InvoiceState, ProcessingStatus, update_progress, SafetyReport, ApprovalInfo
from src.core.logger import logger
from src.core.protocol import AgentResponse
from src.core.config import settings

# Import Agents
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
async def extraction_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"NODE: Extraction | File: {state.file_name}")
    update_progress(state.file_name, "Extraction")
    try:
        resp = extractor.process({
            "file_path": state.file_path,
            "file_name": state.file_name,
            "metadata": state.metadata
        })
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
            
        state.raw_text = resp.payload.get("raw_text")
        state.status = ProcessingStatus.EXTRACTED
        return state
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(str(e))
        return state

@observe(name="safety_node")
async def safety_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    
    logger.info(f"NODE: Safety | File: {state.file_name}")
    update_progress(state.file_name, "Safety Check")
    
    resp = safety.process({"raw_text": state.raw_text, "file_name": state.file_name})
    
    state.redacted_text = resp.payload.get("redacted_text")
    state.safety_report = SafetyReport(**resp.payload.get("safety_report", {}))
    
    status_str = resp.payload.get("status", "safe")
    if status_str == "flagged":
        state.status = ProcessingStatus.FLAGGED
    else:
        state.status = ProcessingStatus.SAFE
    return state

@observe(name="translation_node")
async def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state

    logger.info(f"NODE: Translation | File: {state.file_name}")
    update_progress(state.file_name, "Translation")
    
    try:
        text_input = state.redacted_text or state.raw_text
        resp = await translator.process_async({"raw_text": text_input})
        
        if resp.message_type == "ERROR":
            raise Exception(resp.payload.get("error"))
            
        state.extracted_data = resp.payload.get("extracted_data")
        state.status = ProcessingStatus.TRANSLATED
        return state
    except Exception as e:
        logger.error(f"Translation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(str(e))
        return state

@observe(name="validation_node")
async def validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    
    logger.info(f"NODE: Data Validation | File: {state.file_name}")
    update_progress(state.file_name, "Validation")
    
    resp = await validator.process_async({"extracted_data": state.extracted_data})
    
    is_valid = resp.payload.get("validation_status") == "valid"
    missing = resp.payload.get("missing_fields", [])
    
    state.validation_results = {
        "is_valid": is_valid,
        "missing_fields": missing
    }
    
    if not is_valid:
        state.status = ProcessingStatus.DATA_INVALID
    else:
        state.status = ProcessingStatus.VALIDATED
    return state

@observe(name="business_validation_node")
async def business_validation_node(state: InvoiceState) -> InvoiceState:
    if state.status in [ProcessingStatus.FAILED, ProcessingStatus.DATA_INVALID]: return state
    
    logger.info(f"NODE: Business Validation | File: {state.file_name}")
    update_progress(state.file_name, "Business Validation")
    
    resp = await biz_validator.process_async({"extracted_data": state.extracted_data})
    
    biz_status = resp.payload.get("business_validation_status")
    discrepancies = resp.payload.get("discrepancies", [])
    
    state.validation_results["business_status"] = biz_status
    state.validation_results["discrepancies"] = discrepancies
    
    if discrepancies:
        state.status = ProcessingStatus.BUSINESS_MISMATCH
    return state

@observe(name="reporting_node")
async def reporting_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"NODE: Reporting | File: {state.file_name}")
    update_progress(state.file_name, "Reporting")
    
    resp = await reporter.process_async({
        "file_name": state.file_name,
        "extracted_data": state.extracted_data,
        "validation_report": state.validation_results,
        "safety_report": state.safety_report.model_dump() if state.safety_report else None,
        "approval_info": state.approval_info.model_dump() if state.approval_info else None,
        "metadata": state.metadata
    })
    
    state.report_path = resp.payload
    return state

async def human_review_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"NODE: Human Review | Resuming for {state.file_name}")
    
    if state.status == ProcessingStatus.REJECTED:
        logger.warning(f"Workflow Resumed with REJECTION: {state.approval_info.reason}")
        update_progress(state.file_name, "Rejected", "Processing Halted")
        return state

    if state.approval_info:
        logger.info(f"Workflow Resumed with APPROVAL: {state.approval_info.reason}")
        state.status = ProcessingStatus.APPROVED
        update_progress(state.file_name, "Approved", "Resuming Ingestion")
        return state
        
    logger.warning("Human Review node hit without approval info. This shouldn't happen if paused correctly.")
    return state

@observe(name="ingestion_node")
async def ingestion_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"NODE: Ingestion & Archiving | File: {state.file_name}")
    
    # Check if we should ingest into Vector DB
    should_ingest = False
    
    if state.status == ProcessingStatus.REJECTED:
        logger.info(f"Skipping Vector DB Ingestion for REJECTED invoice: {state.file_name}")
        should_ingest = False
    elif state.status in [ProcessingStatus.APPROVED, ProcessingStatus.COMPLETED]:
        should_ingest = True
    elif state.status in [ProcessingStatus.VALIDATED, ProcessingStatus.SAFE] and not state.validation_results.get("discrepancies"):
        should_ingest = True
    else:
        logger.warning(f"Skipping Ingestion due to Status: {state.status}")
        should_ingest = False

    if should_ingest:
        update_progress(state.file_name, "Ingestion")
        text_content = state.redacted_text or state.raw_text or ""
        approval_note = state.approval_info.reason if state.approval_info else None
        
        if text_content:
            from src.mcp_server.rag import logic_ingest_invoice
            logic_ingest_invoice(
                text=text_content,
                filename=state.file_name,
                metadata=state.metadata,
                approval_context=approval_note
            )
            logger.info(f"Indexed {state.file_name} into Vector DB")

    # Archiving Logic
    dest_dir = settings.PROCESSED_DIR
    dest_path = dest_dir / state.file_name
    
    try:
        if Path(state.file_path).exists():
            shutil.move(state.file_path, str(dest_path))
            logger.info(f"Archived to {dest_path}")
            
            # Move Metadata file if exists
            meta_src = Path(state.file_path).with_suffix(".meta.json")
            if meta_src.exists():
                shutil.move(str(meta_src), str(dest_dir / meta_src.name))
    except Exception as e:
        logger.error(f"Archiving error: {e}")

    # Final Status Update
    final_msg = "Processed & Archived"
    if state.status == ProcessingStatus.REJECTED:
        final_msg = "Rejected & Archived"
    
    if state.status != ProcessingStatus.REJECTED:
        state.status = ProcessingStatus.COMPLETED

    update_progress(state.file_name, "Completed", final_msg)
    return state

def route_after_safety(state: InvoiceState) -> str:
    if state.status == ProcessingStatus.FLAGGED:
        return "reporting"
    if state.status == ProcessingStatus.FAILED:
        return "reporting"
    return "translation"

def route_after_reporting(state: InvoiceState) -> str:
    # Logic: If everything is perfect, go to ingestion.
    # If there are any issues (Invalid, Mismatch, Flagged), go to human_review.
    
    is_valid = state.validation_results.get("is_valid", True)
    has_discrepancies = len(state.validation_results.get("discrepancies", [])) > 0
    is_safe = state.safety_report.is_safe if state.safety_report else True
    
    # If already approved via restart
    if state.approval_info:
        return "ingestion"
        
    if is_valid and not has_discrepancies and is_safe and state.status != ProcessingStatus.FLAGGED:
        return "ingestion"
        
    # Otherwise, trigger HITL
    return "human_review"

def create_invoice_graph():
    wf = StateGraph(InvoiceState)
    
    wf.add_node("extraction", extraction_node)
    wf.add_node("safety", safety_node)
    wf.add_node("translation", translation_node)
    wf.add_node("validation", validation_node)
    wf.add_node("business_validation", business_validation_node)
    wf.add_node("reporting", reporting_node)
    wf.add_node("human_review", human_review_node)
    wf.add_node("ingestion", ingestion_node)
    
    wf.set_entry_point("extraction")
    
    wf.add_edge("extraction", "safety")
    
    wf.add_conditional_edges(
        "safety",
        route_after_safety,
        {
            "translation": "translation",
            "reporting": "reporting"
        }
    )
    
    wf.add_edge("translation", "validation")
    wf.add_edge("validation", "business_validation")
    wf.add_edge("business_validation", "reporting")
    
    wf.add_conditional_edges(
        "reporting",
        route_after_reporting,
        {
            "ingestion": "ingestion",
            "human_review": "human_review"
        }
    )
    
    wf.add_edge("human_review", "ingestion")
    wf.add_edge("ingestion", END)
    
    return wf.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["human_review"]
    )