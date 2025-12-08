import sqlite3
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

# Agents
from src.langgraph_agents.extractor_agent import ExtractorAgent
from src.langgraph_agents.safety_agent import SafetyAgent
from src.adk_agents.translation_agent import TranslationAgent
from src.adk_agents.validation_agent import DataValidationAgent
from src.adk_agents.business_validator_agent import BusinessValidationAgent
from src.adk_agents.reporting_agent import ReportingAgent
from src.langgraph_agents.rag.indexer import IndexingAgent

# Initialize Agents
extractor = ExtractorAgent()
safety = SafetyAgent()
translator = TranslationAgent()
validator = DataValidationAgent()
biz_validator = BusinessValidationAgent()
reporter = ReportingAgent()
indexer = IndexingAgent()

# --- Nodes ---

@observe(name="extraction_node")
def extraction_node(state: InvoiceState) -> InvoiceState:
    update_progress(state.file_name, "Extraction")
    try:
        resp = extractor.process({
            "file_path": state.file_path,
            "file_name": state.file_name,
            "metadata": state.metadata
        })
        if resp.message_type == "ERROR": raise Exception(resp.payload.get("error"))
        state.raw_text = resp.payload.get("raw_text")
        return state
    except Exception as e:
        logger.error(f"Extraction Failed: {e}")
        state.status = ProcessingStatus.FAILED
        state.error_log.append(f"Extraction Error: {e}")
        return state

@observe(name="safety_node")
def safety_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Safety Check")
    try:
        resp = safety.process({"raw_text": state.raw_text, "file_name": state.file_name})
        state.redacted_text = resp.payload.get("redacted_text")
        state.safety_report = SafetyReport(**resp.payload.get("safety_report", {}))
        if not state.safety_report.is_safe: state.status = ProcessingStatus.FLAGGED
        return state
    except Exception as e:
        logger.error(f"Safety Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="translation_node")
def translation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Translation")
    try:
        text = state.redacted_text or state.raw_text
        resp = translator.process({"raw_text": text})
        state.extracted_data = resp.payload.get("extracted_data")
        return state
    except Exception as e:
        logger.error(f"Translation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="validation_node")
def validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Validation")
    try:
        resp = validator.process({"extracted_data": state.extracted_data})
        state.validation_results = {
            "is_valid": resp.payload.get("validation_status") == "valid",
            "missing_fields": resp.payload.get("missing_fields", [])
        }
        return state
    except Exception as e:
        logger.error(f"Validation Failed: {e}")
        state.status = ProcessingStatus.FAILED
        return state

@observe(name="business_validation_node")
def business_validation_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Business Validation")
    try:
        resp = biz_validator.process({"extracted_data": state.extracted_data})
        payload = resp.payload
        state.validation_results["business_status"] = payload.get("business_validation_status")
        state.validation_results["discrepancies"] = payload.get("discrepancies", [])
        if payload.get("discrepancies"): state.validation_results["is_valid"] = False
        return state
    except Exception as e:
        logger.error(f"Business Validation Failed: {e}")
        return state

@observe(name="reporting_node")
def reporting_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Reporting")
    try:
        resp = reporter.process({
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
def ingestion_node(state: InvoiceState) -> InvoiceState:
    if state.status == ProcessingStatus.FAILED: return state
    update_progress(state.file_name, "Ingestion & Archiving")
    
    # 1. RAG Indexing
    try:
        text = state.redacted_text or state.raw_text or ""
        indexer.process({"text": text, "filename": state.file_name})
    except Exception as e:
        logger.warning(f"Indexing failed: {e}")

    # 2. Archive File (Move to Processed)
    try:
        source_path = Path(state.file_path)
        if source_path.exists():
            dest_path = settings.PROCESSED_DIR / source_path.name
            shutil.move(str(source_path), str(dest_path))
            logger.info(f"Archived {state.file_name} to {dest_path}")
            
            # Archive metadata if exists
            meta_src = source_path.with_suffix(".meta.json")
            if meta_src.exists():
                shutil.move(str(meta_src), str(settings.PROCESSED_DIR / meta_src.name))
    except Exception as e:
        logger.error(f"Archiving failed: {e}")

    state.status = ProcessingStatus.COMPLETED
    update_progress(state.file_name, "Completed", "Processed & Archived")
    return state

# --- Routing ---
def route_after_extract(state): return "reporting" if state.status == ProcessingStatus.FAILED else "safety"
def route_after_safety(state): return "reporting" if state.status in [ProcessingStatus.FAILED, ProcessingStatus.FLAGGED] else "translation"

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
    
    # DB Setup with WAL Mode to prevent Disk I/O Errors
    db_path = settings.DATA_DIR / "checkpoints.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    
    from langgraph.checkpoint.sqlite import SqliteSaver
    checkpointer = SqliteSaver(conn)
    
    return wf.compile(checkpointer=checkpointer, interrupt_before=["ingestion"])