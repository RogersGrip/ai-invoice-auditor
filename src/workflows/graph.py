# ===== FILE: src/workflows/graph.py =====
import shutil
import os
import json
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
    logger.info(f"📍 NODE: Extraction | File: {state.file_name}")
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
    logger.info(f"📍 NODE: Safety | File: {state.file_name}")
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
    logger.info(f"📍 NODE: Translation | File: {state.file_name}")
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
    logger.info(f"📍 NODE: Data Validation | File: {state.file_name}")
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
    logger.info(f"📍 NODE: Business Validation | File: {state.file_name}")
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
    logger.info(f"📍 NODE: Reporting | File: {state.file_name}")
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
        return state

@observe(name="ingestion_node")
async def ingestion_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"📍 NODE: Ingestion & Archiving | File: {state.file_name}")
    update_progress(state.file_name, "Ingestion & Archiving")
    
    # 1. Indexing
    if state.status != ProcessingStatus.FAILED:
        try:
            text = state.redacted_text or state.raw_text or ""
            if text:
                indexer.process({"text": text, "filename": state.file_name, "metadata": state.metadata})
                logger.info(f"✅ Indexed {state.file_name}")
        except Exception as e:
            logger.warning(f"Indexing failed: {e}")

    # 2. Archiving (With Metadata Sync)
    try:
        source_path = Path(state.file_path)
        if source_path.exists():
            dest_dir = settings.PROCESSED_DIR
            if not dest_dir.exists(): dest_dir.mkdir(parents=True)
            
            dest_path = dest_dir / source_path.name
            
            # If duplicates, rename with timestamp
            final_name = source_path.name
            if dest_path.exists():
                import time
                timestamp = int(time.time())
                final_name = f"{timestamp}_{source_path.name}"
                dest_path = dest_dir / final_name

            shutil.move(str(source_path), str(dest_path))
            logger.info(f"📂 Archived to {dest_path}")
            
            # --- CRITICAL FIX: Update Report JSON if file was renamed ---
            if final_name != state.file_name:
                try:
                    report_path = settings.OUTPUT_DIR / f"{Path(state.file_name).stem}_report.json"
                    if report_path.exists():
                        with open(report_path, 'r') as f:
                            report_data = json.load(f)
                        
                        # Update filename in report
                        report_data['meta']['file_name'] = final_name
                        report_data['meta']['archived_path'] = str(dest_path)
                        
                        # Save back
                        with open(report_path, 'w') as f:
                            json.dump(report_data, f, indent=2)
                        logger.info(f"📝 Updated report metadata to point to {final_name}")
                except Exception as update_err:
                    logger.warning(f"Failed to update report metadata: {update_err}")

            # Archive metadata file
            meta_src = source_path.with_suffix(".meta.json")
            if meta_src.exists():
                meta_dest_name = Path(final_name).with_suffix(".meta.json").name
                shutil.move(str(meta_src), str(dest_dir / meta_dest_name))
                
    except Exception as e:
        logger.error(f"Archiving failed: {e}")

    state.status = ProcessingStatus.COMPLETED
    update_progress(state.file_name, "Completed", "Processed & Archived")
    return state

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
    
    def route_after_extract(state): return "reporting" if state.status == ProcessingStatus.FAILED else "safety"
    def route_after_safety(state): return "reporting" if state.status in [ProcessingStatus.FAILED, ProcessingStatus.FLAGGED] else "translation"

    wf.add_conditional_edges("extraction", route_after_extract, {"safety": "safety", "reporting": "reporting"})
    wf.add_conditional_edges("safety", route_after_safety, {"translation": "translation", "reporting": "reporting"})
    
    wf.add_edge("translation", "validation")
    wf.add_edge("validation", "business_validation")
    wf.add_edge("business_validation", "reporting")
    wf.add_edge("reporting", "ingestion")
    wf.add_edge("ingestion", END)
    
    return wf.compile(checkpointer=MemorySaver())