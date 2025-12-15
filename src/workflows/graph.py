# ===== FILE: src/workflows/graph.py =====
import shutil
import json
from typing import Literal, Dict, Any
from pathlib import Path
from langgraph.graph import StateGraph, END
from langfuse import observe
from langgraph.checkpoint.memory import MemorySaver

# --- Core Imports ---
from src.core.state import InvoiceState, ProcessingStatus, update_progress, SafetyReport, ApprovalInfo
from src.core.logger import logger
from src.core.protocol import AgentResponse
from src.core.config import settings

# --- Agents ---
from src.langgraph_agents.extractor_agent import ExtractorAgent
from src.langgraph_agents.safety_agent import SafetyAgent
from src.adk_agents.translation_agent import TranslationAgent
from src.adk_agents.validation_agent import DataValidationAgent
from src.adk_agents.business_validator_agent import BusinessValidationAgent
from src.adk_agents.reporting_agent import ReportingAgent
from src.langgraph_agents.rag.indexer import IndexingAgent

# --- Initialize Agents ---
extractor = ExtractorAgent()
safety = SafetyAgent()
translator = TranslationAgent()
validator = DataValidationAgent()
biz_validator = BusinessValidationAgent()
reporter = ReportingAgent()
indexer = IndexingAgent()

# ==============================================================================
# NODES
# ==============================================================================

@observe(name="extraction_node")
async def extraction_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"📍 NODE: Extraction | File: {state.file_name}")
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
    
    logger.info(f"📍 NODE: Safety | File: {state.file_name}")
    update_progress(state.file_name, "Safety Check")
    
    resp = safety.process({"raw_text": state.raw_text, "file_name": state.file_name})
    state.redacted_text = resp.payload.get("redacted_text")
    state.safety_report = SafetyReport(**resp.payload.get("safety_report", {}))
    
    # Map 'safe'/'flagged' to ProcessingStatus
    status_str = resp.payload.get("status", "safe")
    if status_str == "flagged":
        state.status = ProcessingStatus.FLAGGED
    else:
        state.status = ProcessingStatus.SAFE
        
    return state

@observe(name="translation_node")
async def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    
    logger.info(f"📍 NODE: Translation | File: {state.file_name}")
    update_progress(state.file_name, "Translation")
    
    try:
        # Use redacted text if available
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
    
    logger.info(f"📍 NODE: Data Validation | File: {state.file_name}")
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
    
    logger.info(f"📍 NODE: Business Validation | File: {state.file_name}")
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
    # Always generate a report, even if failed, so the user can see *why* it failed in the UI.
    logger.info(f"📍 NODE: Reporting | File: {state.file_name}")
    update_progress(state.file_name, "Reporting")
    
    resp = await reporter.process_async({
        "file_name": state.file_name,
        "extracted_data": state.extracted_data,
        "validation_results": state.validation_results,
        "safety_report": state.safety_report.model_dump() if state.safety_report else None,
        "approval_info": state.approval_info.model_dump() if state.approval_info else None,
        "metadata": state.metadata
    })
    
    state.report_path = resp.payload
    return state

async def human_review_node(state: InvoiceState) -> InvoiceState:
    """
    Passive node that serves as a breakpoint for HITL.
    The workflow pauses BEFORE entering here (via interrupt_before), 
    or we pause execution flow here.
    """
    logger.info(f"🛑 NODE: Human Review | Waiting for Approval for {state.file_name}")
    update_progress(state.file_name, "Awaiting Approval", "Paused")
    # If we are here and have approval info, it means we were resumed!
    if state.approval_info:
        logger.info(f"✅ Resuming with Approval: {state.approval_info.reason}")
        state.status = ProcessingStatus.APPROVED
    return state

@observe(name="ingestion_node")
async def ingestion_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"📍 NODE: Ingestion & Archiving | File: {state.file_name}")
    
    # Skip ingestion if it failed and wasn't approved
    if state.status in [ProcessingStatus.FAILED, ProcessingStatus.DATA_INVALID, ProcessingStatus.BUSINESS_MISMATCH, ProcessingStatus.FLAGGED] and not state.approval_info:
        logger.warning("Skipping Ingestion due to invalid status and no approval.")
        return state

    update_progress(state.file_name, "Ingestion")
    
    # 1. Indexing (MCP)
    text_content = state.redacted_text or state.raw_text or ""
    approval_note = state.approval_info.reason if state.approval_info else None
    
    if text_content:
        # Use the logic function directly, NOT the decorated tool
        from src.mcp_server.rag import logic_ingest_invoice
        logic_ingest_invoice(
            text=text_content, 
            filename=state.file_name, 
            metadata=state.metadata,
            approval_context=approval_note
        )
        logger.info(f"✅ Indexed {state.file_name} into Vector DB")

    # 2. Archiving
    dest_dir = settings.PROCESSED_DIR
    dest_path = dest_dir / state.file_name
    try:
        if Path(state.file_path).exists():
            shutil.move(state.file_path, str(dest_path))
            logger.info(f"📂 Archived to {dest_path}")
            
            # Move metadata if exists
            meta_src = Path(state.file_path).with_suffix(".meta.json")
            if meta_src.exists():
                shutil.move(str(meta_src), str(dest_dir / meta_src.name))
    except Exception as e:
        logger.error(f"Archiving error: {e}")

    state.status = ProcessingStatus.COMPLETED
    update_progress(state.file_name, "Completed", "Processed & Archived")
    return state

# ==============================================================================
# ROUTING LOGIC
# ==============================================================================

def route_after_safety(state: InvoiceState) -> str:
    if state.status == ProcessingStatus.FLAGGED:
        return "reporting" # Go straight to report if unsafe
    if state.status == ProcessingStatus.FAILED:
        return "reporting"
    return "translation"

def route_after_reporting(state: InvoiceState) -> str:
    # If everything is green, go to ingestion
    if state.status in [ProcessingStatus.VALIDATED, ProcessingStatus.SAFE, ProcessingStatus.EXTRACTED, ProcessingStatus.TRANSLATED]:
        # Note: Validated implies Safe+Extracted+Translated
        if state.validation_results.get("is_valid", True) and not state.validation_results.get("discrepancies"):
             return "ingestion"
    
    # If we already have approval (e.g. injected before reporting run?), go to ingestion
    if state.approval_info:
        return "ingestion"

    # Otherwise (Failed, Flagged, Invalid, Mismatch), go to Human Review
    return "human_review"

# ==============================================================================
# GRAPH CONSTRUCTION
# ==============================================================================

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
    
    # Extraction -> Safety
    wf.add_edge("extraction", "safety")
    
    # Safety -> (Translation OR Reporting)
    wf.add_conditional_edges(
        "safety", 
        route_after_safety, 
        {
            "translation": "translation",
            "reporting": "reporting"
        }
    )
    
    # Main Flow
    wf.add_edge("translation", "validation")
    wf.add_edge("validation", "business_validation")
    wf.add_edge("business_validation", "reporting")
    
    # Reporting -> (Ingestion OR Human Review)
    wf.add_conditional_edges(
        "reporting",
        route_after_reporting,
        {
            "ingestion": "ingestion",
            "human_review": "human_review"
        }
    )
    
    # Human Review -> Ingestion (Assumes approval happened during pause)
    wf.add_edge("human_review", "ingestion")
    
    wf.add_edge("ingestion", END)

    # Compile with Memory Saver and Interrupt logic
    # We interrupt BEFORE 'human_review' so the system pauses and waits for API call
    return wf.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["human_review"]
    )