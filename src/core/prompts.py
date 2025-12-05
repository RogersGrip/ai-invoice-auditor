from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(prompt_name: str) -> str:
    """Loads a raw prompt file from src/prompts/ directory
    
    Args:
        prompt_name (str): The filename of the prompt to load.
        
    Returns:
        str: The content of the prompt file.
    """
    file_path = PROMPTS_DIR / prompt_name

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_name}")
    
    return file_path.read_text(encoding="utf-8").strip()