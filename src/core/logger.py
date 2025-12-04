import sys
from loguru import logger
from pathlib import Path

def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return current.parent.parent.parent

PROJECT_ROOT = find_project_root(Path(__file__).resolve())
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()

logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level="DEBUG"
)

logger.add(
    LOG_DIR / "app_events.json",
    serialize=True,
    level="DEBUG",
    rotation="10 MB",
    retention="10 days",
    compression="zip"
)

logger.add(
    LOG_DIR / "app_debug.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB"
)

def get_logger():
    return logger