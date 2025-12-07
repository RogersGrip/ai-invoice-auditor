from langfuse import observe
from src.core.state import InvoiceState, ProcessingStatus
from src.core.config import settings
from src.core.logger import logger
from src.agents.extractor import ExtractorAgent, MockExtractorAgent
from src.agents.data_validator import DataValidationAgent
from src.agents.business_validator import BusinessValidationAgent
from src.agents.reporter import ReporterAgent
from src.agents.adk_translator_wrapper import ADKTranslatorWrapper

# Initialize Agents
if settings.USE_MOCK_DATA:
    logger.info("Using Mock Extractor Agent")
    extractor = MockExtractorAgent()
else:
    extractor = ExtractorAgent()

# Swapped to ADK Wrapper
translator = ADKTranslatorWrapper()

# Split Validators
data_validator = DataValidationAgent()
business_validator = BusinessValidationAgent()

reporter = ReporterAgent()

@observe(name="extractor_node")
def extractor_node(state: InvoiceState) -> dict:
    from src.core.state import update_progress
    update_progress(state.file_name, "Extraction", "Extracting OCR text...")
    
    resp = extractor.process({
        "file_path": state.file_path,
        "file_name": state.file_name
    })
    status = ProcessingStatus.EXTRACTED if resp.content else ProcessingStatus.FAILED
    return {"raw_text": resp.content, "status": status}

@observe(name="translator_node")
def translator_node(state: InvoiceState) -> dict:
    from src.core.state import update_progress
    update_progress(state.file_name, "Translation", "Standardizing data with LLM...")

    resp = translator.process({"raw_text": state.raw_text})
    if not resp.content or hasattr(resp.content, "structured_data") and not resp.content.structured_data.get("invoice_no"):
         # Basic check if translation yielded something useful
         pass
         
    # ADK Wrapper returns Pydantic model directly
    return {"extracted_data": resp.content, "status": ProcessingStatus.TRANSLATED}

@observe(name="data_validator_node")
def data_validator_node(state: InvoiceState) -> dict:
    from src.core.state import update_progress
    update_progress(state.file_name, "Validation", "Checking data integrity...")

    resp = data_validator.process({"extracted_data": state.extracted_data})
    is_valid = resp.content.get("is_valid", False)
    
    # Store missing fields in "flagged_issues" if any
    missing = resp.content.get("missing_fields", [])
    validation_results = [f"Missing Field: {m}" for m in missing]
    
    return {
        "status": ProcessingStatus.VALIDATED if is_valid else ProcessingStatus.DATA_INVALID, 
        "validation_results": validation_results
    }

@observe(name="business_validator_node")
def business_validator_node(state: InvoiceState) -> dict:
    resp = business_validator.process({"extracted_data": state.extracted_data})
    
    discrepancies = resp.content.get("discrepancies", [])
    
    # Update existing validation results
    current_results = state.validation_results or []
    current_results.extend(discrepancies)
    
    final_status = ProcessingStatus.VALIDATED if not current_results else ProcessingStatus.FLAGGED
    
    return {
        "validation_results": current_results,
        "status": final_status
    }

@observe(name="reporter_node")
def reporter_node(state: InvoiceState) -> dict:
    from src.core.state import update_progress
    update_progress(state.file_name, "Reporting", "Generating PDF Report...")

    # Construct Validation Report structure expected by Reporter
    is_valid = len(state.validation_results) == 0
    val_report = {
        "is_valid": is_valid,
        "discrepancies": state.validation_results
    }

    resp = reporter.process({
        "extracted_data": state.extracted_data, 
        "file_name": state.file_name,
        "overall_status": state.status,
        "validation_report": val_report,
        "metadata": state.metadata
    })
    return {"report_path": resp.content, "status": ProcessingStatus.COMPLETED}

# Added Indexing/Ingestion Node
from src.agents.rag.indexer import IndexingAgent
indexer = IndexingAgent()

@observe(name="ingestor_node")
def ingestor_node(state: InvoiceState) -> dict:
    from src.core.state import update_progress
    update_progress(state.file_name, "Ingestion", "Indexing to Vector DB...")

    # We index the raw text so RAG can retrieve it
    # We could also index the JSON/Structured data stringified if preferred
    text_to_index = state.raw_text
    
    # If raw text is empty/failed, maybe index str(extracted_data)?
    if not text_to_index and state.extracted_data:
        text_to_index = str(state.extracted_data)
        
    resp = indexer.process({
        "text": text_to_index,
        "filename": state.file_name,
        "metadata": state.metadata
    })
    
    # Update progress to Completed
    from src.core.state import update_progress
    update_progress(state.file_name, "Completed", "Processed successfully.")
    
    # Status remains COMPLETED
    return {}