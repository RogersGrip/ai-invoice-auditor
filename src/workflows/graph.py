# ===== FILE: src/workflows/graph.py =====
import shutil
import os
from typing import Literal
from pathlib import Path
from langgraph.graph import StateGraph, END
from langfuse import observe
from src.core.state import InvoiceState, ProcessingStatus, update_progress, SafetyReport
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

# Import MemorySaver for Async Compatibility
from langgraph.checkpoint.memory import MemorySaver

# Initialize Agents
extractor = ExtractorAgent()
safety = SafetyAgent()
translator = TranslationAgent()
validator = DataValidationAgent()
biz_validator = BusinessValidationAgent()
reporter = ReportingAgent()
indexer = IndexingAgent()

# --- Async Nodes ---

@observe(name="extraction_node")
async def extraction_node(state: InvoiceState) -> InvoiceState:
    update_progress(state.file_name, "Extraction")
    try:
        resp = extractor.process({
            "file_path": state.file_path,
            "file_name": state.file_name,
            "metadata": state.metadata
        })
        if resp.message_type == "ERROR": raise Exception(resp.payload.get("error"))
        state.raw_text = resp.payload.get("raw_text")
        state.status = ProcessingStatus.EXTRACTED
        return state
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Extraction Error: {e}")
        return state

@observe(name="safety_node")
async def safety_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Safety Check")
    try:
        resp = safety.process({"raw_text": state.raw_text, "file_name": state.file_name})
        state.redacted_text = resp.payload.get("redacted_text")
        state.safety_report = SafetyReport(**resp.payload.get("safety_report", {}))
        
        if not state.safety_report.is_safe: 
            state.status = ProcessingStatus.FLAGGED
        else:
            state.status = ProcessingStatus.SAFE
            
        return state
    except Exception as e:
        logger.error(f"Safety Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="translation_node")
async def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Translation")
    try:
        text = state.redacted_text or state.raw_text
        resp = await translator.process_async({"raw_text": text})
        
        if resp.message_type == "ERROR": raise Exception(resp.payload.get("error"))
        
        state.extracted_data = resp.payload.get("extracted_data")
        state.status = ProcessingStatus.TRANSLATED
        return state
    except Exception as e:
        logger.error(f"Translation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="validation_node")
async def validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Validation")
    try:
        resp = await validator.process_async({"extracted_data": state.extracted_data})
        
        if resp.message_type == "ERROR": raise Exception(resp.payload.get("error"))
        
        state.validation_results = {
            "is_valid": resp.payload.get("validation_status") == "valid",
            "missing_fields": resp.payload.get("missing_fields", [])
        }
        state.status = ProcessingStatus.VALIDATED
        return state
    except Exception as e:
        logger.error(f"Validation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="business_validation_node")
async def business_validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Business Validation")
    try:
        resp = await biz_validator.process_async({"extracted_data": state.extracted_data})
        
        payload = resp.payload
        state.validation_results["business_status"] = payload.get("business_validation_status")
        state.validation_results["discrepancies"] = payload.get("discrepancies", [])
        
        if payload.get("discrepancies"): 
            state.validation_results["is_valid"] = False
            state.status = ProcessingStatus.BUSINESS_MISMATCH
            
        return state
    except Exception as e:
        logger.error(f"Business Validation Failed: {e}")
        state.validation_results["business_status"] = "error"
        return state

@observe(name="reporting_node")
async def reporting_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Reporting")
    try:
        resp = await reporter.process_async({
            "file_name": state.file_name,
            "extracted_data": state.extracted_data,
            "validation_results": state.validation_results,
            "safety_report": state.safety_report.model_dump() if state.safety_report else None,
            "metadata": state.metadata
        })
        state.report_path = resp.payload
        return state
    except Exception as e:
        logger.error(f"Reporting Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="ingestion_node")
async def ingestion_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Ingestion & Archiving")
    
    # 1. Indexing
    try:
        text = state.redacted_text or state.raw_text or ""
        indexer.process({"text": text, "filename": state.file_name, "metadata": state.metadata})
        logger.info(f"Indexed {state.file_name}")
    except Exception as e:
        logger.warning(f"Indexing failed: {e}")

    # 2. Archiving (Move File)
    try:
        source_path = Path(state.file_path)
        if source_path.exists():
            dest_path = settings.PROCESSED_DIR / source_path.name
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"✅ Archived {state.file_name} to {dest_path}")
            
            meta_src = source_path.with_suffix(".meta.json")
            if meta_src.exists():
                shutil.move(str(meta_src), str(settings.PROCESSED_DIR / meta_src.name))
        else:
            logger.warning(f"File {state.file_path} not found for archiving.")
            
    except Exception as e:
        logger.error(f"Archiving failed: {e}")

    state.status = ProcessingStatus.COMPLETED
    update_progress(state.file_name, "Completed", "Processed & Archived")
    return state

# --- Edge Logic ---
def route_after_extract(state): 
    return "reporting" if state.status == ProcessingStatus.FAILED else "safety"

def route_after_safety(state): 
    return "reporting" if state.status in [ProcessingStatus.FAILED, ProcessingStatus.FLAGGED] else "translation"

# --- Graph Construction ---
def create_invoice_graph():
    wf = StateGraph(InvoiceState)
    
    wf.add_node("extraction", extraction_node)
    wf.add_node("safety", safety_node)
    wf.add_node("translation", translation_node)
    wf.add_node("validation", validation_node)
    wf.add_node("business_validation", business_validation_node)
    wf.add_node("reporting", reporting_node)
    wf.add_node("ingestion", ingestion_node)
    
    wf.set_entry_point("extraction")
    
    wf.add_conditional_edges("extraction", route_after_extract, {"safety": "safety", "reporting": "reporting"})
    wf.add_conditional_edges("safety", route_after_safety, {"translation": "translation", "reporting": "reporting"})
    
    wf.add_edge("translation", "validation")
    wf.add_edge("validation", "business_validation")
    wf.add_edge("business_validation", "reporting")
    wf.add_edge("reporting", "ingestion")
    wf.add_edge("ingestion", END)
    
    # Use MemorySaver instead of SqliteSaver to support async
    checkpointer = MemorySaver()
    
    return wf.compile(checkpointer=checkpointer)