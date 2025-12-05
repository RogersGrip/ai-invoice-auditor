from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(prompt_name: str) -> str:
    """Loads a raw prompt file from src/prompts/."""
    file_path = PROMPTS_DIR / prompt_name
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_name}")
    return file_path.read_text(encoding="utf-8").strip()