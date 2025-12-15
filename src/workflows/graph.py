import shutil
import os
import json
from pathlib import Path
from langgraph.graph import StateGraph, END
from langfuse import observe
from src.core.state import InvoiceState, ProcessingStatus, update_progress, SafetyReport
from src.core.logger import logger
from src.core.config import settings
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

@observe(name="ingestion_node")
async def ingestion_node(state: InvoiceState) -> InvoiceState:
    logger.info(f"📍 NODE: Ingestion & Archiving | File: {state.file_name}")
    update_progress(state.file_name, "Ingestion & Archiving")
    
    # Check for Manual Approval Overrides
    approval_meta = state.metadata.get("approval_context", {})
    if approval_meta:
        logger.info(f"☝️  Manual Approval Detected: {approval_meta.get('comment')}")
        state.status = ProcessingStatus.COMPLETED

    if state.status == ProcessingStatus.COMPLETED or state.status == "APPROVED":
        try:
            # Prepare text for Indexing (RAI Safe)
            text_payload = f"""
            FILE: {state.file_name}
            STATUS: {state.status}
            METADATA: {json.dumps(state.metadata)}
            APPROVAL_NOTE: {approval_meta.get('comment', 'N/A')}
            CONTENT:
            {state.redacted_text or state.raw_text}
            """
            
            indexer.process({
                "text": text_payload, 
                "filename": state.file_name, 
                "metadata": {**state.metadata, "approval_reason": approval_meta.get("comment")}
            })
            logger.info(f"✅ Indexed {state.file_name} into RAG System")
            
        except Exception as e:
            logger.warning(f"Indexing failed: {e}")

        # Archiving Logic
        try:
            source_path = Path(state.file_path)
            if source_path.exists():
                dest_dir = settings.PROCESSED_DIR
                if not dest_dir.exists(): dest_dir.mkdir(parents=True)
                
                timestamp = int(os.path.getmtime(source_path))
                final_name = f"{timestamp}_{source_path.name}"
                dest_path = dest_dir / final_name
                
                shutil.move(str(source_path), str(dest_path))
                logger.info(f"📂 Archived to {dest_path}")
                
                # Update Report Pointer
                report_path = settings.OUTPUT_DIR / f"{Path(state.file_name).stem}_report.json"
                if report_path.exists():
                    with open(report_path, 'r+') as f:
                        data = json.load(f)
                        data['meta']['archived_path'] = str(dest_path)
                        data['meta']['status'] = "APPROVED" if approval_meta else state.status
                        f.seek(0)
                        json.dump(data, f, indent=2)
                        f.truncate()

        except Exception as e:
            logger.error(f"Archiving failed: {e}")
            
    return state

# ... (Previous node definitions extraction_node, safety_node etc. remain similar but imports updated) ...

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