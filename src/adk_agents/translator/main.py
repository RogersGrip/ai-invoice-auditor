import uvicorn
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from loguru import logger
from src.core.logger import get_logger

from src.adk_agents.translator.schemas import TranslationRequest, TranslationResponse
from src.adk_agents.translator.service import TranslatorService

# Setup
load_dotenv()
get_logger()

app = FastAPI(title="Invoice Translator Agent (ADK)", version="1.0")
service = TranslatorService()

# Endpoint Definitions
@app.post("/translate", response_model=TranslationResponse)
async def translate_endpoint(request: TranslationRequest):
    """Translate an invoice to a specified language"""
    try:
        return service.process(request)
    except Exception as e:
        logger.exception("Translation Agent Failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "active", "agent": "translator"}

if __name__ == "__main__":
    # Run the server on port 8001
    uvicorn.run("src.adk_agents.translator.main:app", host="0.0.0.0", port=8001, reload=True)