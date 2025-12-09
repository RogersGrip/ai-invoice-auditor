from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = "AI Invoice Auditor"
    VERSION: str = "1.0.0"
    ENV: Literal["dev", "prod", "test"] = "dev"
    
    # --- Model Configuration ---
    # Defaulting to Bedrock/Cohere as requested
    MODEL_PROVIDER: Literal["bedrock", "ollama"] = "bedrock"
    
    # Model IDs (Cohere Command R+ on Bedrock)
    TRANSLATION_MODEL: str = "cohere.command-r-plus-v1:0"
    VALIDATION_MODEL: str = "cohere.command-r-plus-v1:0"
    REPORTING_MODEL: str = "cohere.command-r-plus-v1:0"
    SAFETY_MODEL: str = "cohere.command-r-plus-v1:0"
    
    # Embeddings
    EMBEDDING_MODEL: str = "amazon.titan-embed-text-v1"
    
    # Ollama Fallbacks (Optional)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # --- Paths ---
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    INVOICE_WATCH_DIR: Path = DATA_DIR / "invoices"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    OUTPUT_DIR: Path = BASE_DIR / "outputs" / "reports"
    QDRANT_PATH: Path = DATA_DIR / "qdrant_storage"
    LOG_DIR: Path = BASE_DIR / "logs"

    # --- Observability ---
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure directories exist
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)