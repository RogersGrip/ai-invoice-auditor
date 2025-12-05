import fitz 
from pathlib import Path
from loguru import logger

class OCREngine:
    def extract(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        logger.info(f"Extracting text from: {path.name}")
        
        try:
            if path.suffix.lower() == ".pdf":
                return self._extract_pdf(path)
            elif path.suffix.lower() in [".txt", ".json", ".md"]:
                return path.read_text(encoding="utf-8")
            else:
                return f"[ERROR] Unsupported file format: {path.suffix}"
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise

    def _extract_pdf(self, path: Path) -> str:
        text_content = []
        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    text_content.append(f"--- PAGE {page_num + 1} ---\n{text}")
                else:
                    text_content.append(f"--- PAGE {page_num + 1} [IMAGE CONTENT DETECTED] ---")
        
        return "\n".join(text_content)