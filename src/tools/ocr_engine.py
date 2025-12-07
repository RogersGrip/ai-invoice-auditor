import fitz 
import pytesseract
from PIL import Image
import io
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
            elif path.suffix.lower() in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
                 return self._extract_image(path)
            elif path.suffix.lower() in [".txt", ".json", ".md"]:
                return path.read_text(encoding="utf-8")
            else:
                return f"[ERROR] Unsupported file format for text extraction: {path.suffix}"
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return f"[ERROR: Extraction Failed: {str(e)}]"

    def _extract_pdf(self, path: Path) -> str:
        text_content = []
        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc):
                # 1. Try native text extraction
                text = page.get_text()
                
                # 2. If empty, use OCR (Tesseract)
                if not text.strip():
                    logger.info(f"Page {page_num + 1} has no text layer. Attempting OCR...")
                    try:
                        pix = page.get_pixmap()
                        img_data = pix.tobytes("png")
                        image = Image.open(io.BytesIO(img_data))
                        text = pytesseract.image_to_string(image)
                        
                        if text.strip():
                             logger.success(f"OCR successful for Page {page_num + 1}")
                        else:
                             logger.warning(f"OCR found no text on Page {page_num + 1}")
                    except Exception as ocr_err:
                         logger.error(f"OCR Failed for Page {page_num + 1}: {ocr_err}")
                         text = f"[OCR FAILED: {ocr_err}]"

                if text.strip():
                    text_content.append(f"--- PAGE {page_num + 1} ---\n{text}")
                else:
                    text_content.append(f"--- PAGE {page_num + 1} [NO TEXT/IMAGE CONTENT] ---")
        
        return "\n".join(text_content)

    def _extract_image(self, path: Path) -> str:
        try:
            image = Image.open(path)
            text = pytesseract.image_to_string(image)
            return f"--- IMAGE EXTRACT ({path.name}) ---\n{text}"
        except ImportError:
             return "[ERROR: Pytesseract not installed]"
        except Exception as e:
            error_msg = str(e)
            if "tesseract is not installed" in error_msg or "not in your PATH" in error_msg:
                 logger.warning(f"Tesseract binary missing: {error_msg}")
                 return "[ERROR: Tesseract OCR binary not found on system. Please install Tesseract-OCR.]"
            
            logger.error(f"Image OCR Failed: {e}")
            raise e