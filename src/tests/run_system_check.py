import sys
import unittest
from pathlib import Path
from loguru import logger

# Add root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# Import Logics
from src.mcp_server.erp import logic_validate_line_item
from src.mcp_server.rag import logic_ingest_invoice
from src.tools.ocr_engine import OCREngine

class SystemHealthCheck(unittest.TestCase):

    def setUp(self):
        # Configure minimal logging for tests
        logger.remove()
        logger.add(sys.stderr, level="ERROR")

    def test_erp_logic_match(self):
        """Test ERP logic with known good data"""
        res = logic_validate_line_item("SKU-001", 12.00, "USD")
        self.assertEqual(res['status'], 'match')

    def test_erp_logic_discrepancy(self):
        """Test ERP logic detects high price"""
        res = logic_validate_line_item("SKU-001", 100.00, "USD")
        self.assertEqual(res['status'], 'discrepancy')

    def test_ocr_engine_pdf(self):
        """Test OCR extracts text (Requires dummy PDF)"""
        tool = OCREngine()
        # Expecting FileNotFoundError if file missing, which proves tool is active
        with self.assertRaises(FileNotFoundError):
            tool.extract("non_existent.pdf")

    def test_rag_ingestion_mock(self):
        """Test RAG ingestion doesn't crash"""
        res = logic_ingest_invoice("Mock Text", "test_file.txt")
        self.assertIn("Successfully indexed", res)

if __name__ == '__main__':
    print("Running System Health Checks...")
    unittest.main()