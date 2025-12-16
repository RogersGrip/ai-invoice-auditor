from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = "AI Invoice Auditor"
    VERSION: str = "1.0.0"
    ENV: Literal["dev", "prod", "test"] = "dev"
    
    MODEL_PROVIDER: Literal["bedrock", "ollama"] = "bedrock"
    
    # Models
    TRANSLATION_MODEL: str = "cohere.command-r-plus-v1:0"
    VALIDATION_MODEL: str = "cohere.command-r-plus-v1:0"
    REPORTING_MODEL: str = "cohere.command-r-plus-v1:0"
    SAFETY_MODEL: str = "cohere.command-r-plus-v1:0"
    
    # CHANGED: Titan was denied, switching to Cohere Embeddings which should match your model permissions
    EMBEDDING_MODEL: str = "cohere.embed-english-v3"
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    INVOICE_WATCH_DIR: Path = DATA_DIR / "invoices"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    OUTPUT_DIR: Path = BASE_DIR / "outputs" / "reports"
    QDRANT_PATH: Path = DATA_DIR / "qdrant_storage"
    LOG_DIR: Path = BASE_DIR / "logs"
    
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)