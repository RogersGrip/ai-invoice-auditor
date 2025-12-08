import sys
from loguru import logger

def setup_logger(log_file: str = "logs/invoice_auditor.log", level: str = "INFO"):
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        enqueue=True
    )
    logger.add(
        log_file,
        rotation="10 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        level=level,
        serialize=True,
        enqueue=True
    )
    return logger

logger = setup_logger()