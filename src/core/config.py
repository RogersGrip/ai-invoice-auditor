import yaml
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger

class AgentConfig(BaseModel):
    persona_role: str
    core_responsibility: str

class ValidationRules(BaseModel):
    required_fields: Dict[str, List[str]]
    data_types: Dict[str, str]
    tolerances: Dict[str, float]
    accepted_currencies: List[str]
    currency_symbol_map: Dict[str, str]
    validation_policies: Dict[str, Any]

class ReportingConfig(BaseModel):
    include_translation_confidence: bool
    include_discrepancy_summary: bool
    report_format: str
    output_dir: str

class LoggingConfig(BaseModel):
    enable_audit_log: bool
    log_file: str
    log_level: str

class AppConfig(BaseModel):
    agents: Dict[str, AgentConfig] = {}
    rules: ValidationRules | None = None
    reporting: ReportingConfig | None = None
    logging: LoggingConfig | None = None

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    TRANSLATION_MODEL: str
    VALIDATION_MODEL: str
    REPORTING_MODEL: str
    EMBEDDING_MODEL: str
    
    TRANSLATOR_AGENT_URL: str = "http://localhost:8001"
    
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "config")
    
    config: AppConfig = Field(default_factory=AppConfig)

    def load_yaml_configs(self):
        try:
            rules_path = self.CONFIG_DIR / "rules.yaml"
            if rules_path.exists():
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules_data = yaml.safe_load(f)
                    self.config.rules = ValidationRules(**rules_data)
                    
                    if "reporting" in rules_data:
                        self.config.reporting = ReportingConfig(**rules_data["reporting"])
                    if "logging" in rules_data:
                        self.config.logging = LoggingConfig(**rules_data["logging"])

            persona_path = self.CONFIG_DIR / "persona_invoice_agent.yaml"
            if persona_path.exists():
                with open(persona_path, "r", encoding="utf-8") as f:
                    raw_personas = yaml.safe_load(f)
                    for agent_name, details in raw_personas.items():
                        self.config.agents[agent_name] = AgentConfig(
                            persona_role=details.get("persona_role", "Unknown"),
                            core_responsibility=details.get("core_responsibility", "None")
                        )
            
            logger.info("System Configuration loaded successfully.")

        except Exception as e:
            logger.critical(f"Failed to load configuration: {e}")
            raise

settings = Settings()
settings.load_yaml_configs()