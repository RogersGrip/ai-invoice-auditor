import fitz 
from pathlib import Path
from loguru import logger

class OCREngine:
    def extract(self, file_path: str) -> str:
        """Extract text from various document formats.
        
        Args:
            file_path (str): The path to the document file.

        Returns:
            str: The extracted text content.
        """
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
                return f"[ERROR] Unsupported file format for text extraction: {path.suffix}"
        
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from a PDF file using PyMuPDF.
        
        Args:
            path (Path): The path to the PDF file.
            
        Returns:
            str: The extracted text content from the PDF.
        """
        text_content = []
        
        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc):
                text = page.get_text()
        
                if text.strip():
                    text_content.append(f"--- PAGE {page_num + 1} ---\n{text}")
        
                else:
                    logger.warning(f"Page {page_num + 1} contains no extractable text (Image-only).")
                    text_content.append(f"--- PAGE {page_num + 1} [NO TEXT LAYER] ---")
        
        return "\n".join(text_content)