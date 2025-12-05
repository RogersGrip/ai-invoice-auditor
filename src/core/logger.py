import sys
import warnings
from loguru import logger
from pathlib import Path

def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return current.parent.parent.parent

# 1. Global Warning Suppression (Run once on import)
def configure_warnings():
    warnings.simplefilter("ignore")
    # Specific filters for stubborn libraries
    warnings.filterwarnings("ignore", module="litellm")
    warnings.filterwarnings("ignore", module="pydantic")

configure_warnings()

# 2. Path Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 3. Logger Configuration
def configure_logger():
    logger.remove()
    
    # Console: High level info + Colors
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # File: Verbose Trace (Everything for debugging)
    logger.add(
        LOG_DIR / "trace.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip"
    )

    # File: Audit Log (Only Validation Results)
    logger.add(
        LOG_DIR / "audit.log",
        filter=lambda record: "AUDIT" in record["extra"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO"
    )

    return logger

# Singleton
logger = configure_logger()

def get_logger():
    return logger