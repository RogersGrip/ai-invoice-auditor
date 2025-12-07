from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "AI Invoice Auditor"
    VERSION: str = "0.1.0"
    ENV: Literal["dev", "prod", "test"] = "dev"
    
    # Model Configuration
    MODEL_PROVIDER: Literal["bedrock", "ollama"] = "ollama"
    
    # Bedrock / Generic LLM
    TRANSLATION_MODEL: str = "cohere.command-r-plus-v1:0"
    VALIDATION_MODEL: str = "cohere.command-r-plus-v1:0"
    REPORTING_MODEL: str = "cohere.command-r-plus-v1:0"
    EMBEDDING_MODEL: str = "amazon.titan-embed-text-v1"
    
    # Ollama Specific Overrides (Defaults)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3:8b"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Dev Flags
    USE_MOCK_DATA: bool = False

    # Vector DB
    QDRANT_PATH: str = "./data/qdrant_storage"
    
    # Paths
    INVOICE_WATCH_DIR: str = "data/invoices"
    PROCESSED_DIR: str = "data/processed"
    OUTPUT_DIR: str = "outputs/reports"

    # Langfuse
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str | None = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
