import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException, Body
from src.core.logger import logger
from src.core.config import settings
from src.core.state import InvoiceState
from src.workflows.graph import create_invoice_graph

app = FastAPI(title="AI Invoice Auditor Server")
graph_app = create_invoice_graph()

@app.post("/v1/approve")
async def approve_invoice(payload: dict = Body(...)):
    file_name = payload.get("file_name")
    comment = payload.get("comment", "Manual Approval")
    
    if not file_name: raise HTTPException(400, "file_name required")
    
    logger.info(f"🔓 Manual Approval Request for {file_name} | Reason: {comment}")
    
    # Identify Thread ID (Assuming filename based ID strategy from main.py)
    # In a real persistence layer, we would lookup the thread_id.
    # Here we simulate finding the suspended state.
    
    # Re-trigger Ingestion with Approval Context
    # Since we use MemorySaver, state is lost on restart. 
    # This simulates the 'Action' by re-running ingestion logic specifically.
    
    try:
        from src.langgraph_agents.rag.indexer import IndexingAgent
        indexer = IndexingAgent()
        
        # Simulate State for Indexing
        indexer.process({
            "text": f"MANUAL APPROVAL for {file_name}\nReason: {comment}",
            "filename": file_name,
            "metadata": {"approval_status": "APPROVED", "approver_comment": comment}
        })
        
        # Update JSON Report
        base = Path(file_name).stem
        candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*_report.json"))
        if candidates:
            with open(candidates[0], 'r+') as f:
                data = json.load(f)
                data['meta']['status'] = "APPROVED"
                data['meta']['approval_comment'] = comment
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
                
        return {"status": "success", "message": f"Approved {file_name} and Indexed."}
        
    except Exception as e:
        logger.error(f"Approval Processing Failed: {e}")
        raise HTTPException(500, str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)