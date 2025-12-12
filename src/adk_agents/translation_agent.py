# translation_agent.py

import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from agent_adk import AgentADK
from src.core.protocol import AgentResponse
from src.tools.tools import LangBridgeTool
from src.core.logger import logger


class TranslationAgent(AgentADK):
    
    def __init__(self, model: str = None):
        instruction = """You are a Translation Agent responsible for converting invoice text to structured JSON format.

Your task is to extract and standardize invoice information from raw text into a structured format.
Process the text and ensure all fields are properly extracted and formatted."""
        
        super().__init__(
            name="Translation_Agent",
            instruction=instruction,
            model=model or "bedrock/amazon.nova-lite-v1:0",
            tools=None,
            verbose=False
        )
        
        self.bridge_tool = LangBridgeTool()
    
    async def process_async(self, inputs: Dict[str, Any]) -> AgentResponse:
        raw_text = inputs.get("raw_text") or inputs.get("payload", {}).get("raw_text")
        context_id = inputs.get("context_id", str(uuid.uuid4()))
        
        if not raw_text:
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Translation Agent",
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": "No text to translate"},
                context_id=context_id
            )
        
        logger.info(f"[Translation Agent] Translating text...")
        
        try:
            result = self.bridge_tool.run({"text": raw_text})
            
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Translation Agent",
                target_agent="Data Validation Agent",
                message_type="TASK_HANDOFF",
                payload=result,
                context_id=context_id
            )
            
        except Exception as e:
            logger.error(f"Translation Error: {e}")
            return AgentResponse(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_agent="Translation Agent",
                target_agent="Error Handler",
                message_type="ERROR",
                payload={"error": str(e)},
                context_id=context_id
            )
    
    def process(self, inputs: Dict[str, Any]) -> AgentResponse:
        import asyncio
        return asyncio.run(self.process_async(inputs))


if __name__ == "__main__":
    import asyncio
    
    async def test_agent():
        agent = TranslationAgent()
        agent.print_info()
        
        print("\n" + "="*70)
        print("TRANSLATION AGENT TEST - MULTILINGUAL INVOICES")
        print("="*70 + "\n")
        
        french_invoice = """
        FACTURE
        
        Numéro de facture: INV-2024-12345
        Date: 12 décembre 2024
        
        Facturé à:
        ABC Corporation
        123 Rue des Affaires
        Paris, 75001
        
        Fournisseur: XYZ Fournitures SARL
        ID Fournisseur: VEND-789
        
        Articles:
        1. Fournitures de bureau - Code article: OFF-001
           Quantité: 50 unités à 10,00 € chacune = 500,00 €
        
        2. Équipement informatique - Code article: COMP-002
           Quantité: 5 unités à 300,00 € chacune = 1 500,00 €
        
        3. Mobilier - Code article: FURN-003
           Quantité: 10 unités à 150,00 € chacune = 1 500,00 €
        
        Sous-total: 3 500,00 €
        TVA (20%): 700,00 €
        Montant total: 4 200,00 €
        
        Conditions de paiement: 30 jours nets
        Devise: EUR
        """
        
        spanish_invoice = """
        FACTURA
        
        Número de factura: INV-ES-999
        Fecha: 12 de diciembre de 2024
        
        Facturar a:
        Empresa ABC
        Calle Principal 456
        Madrid, 28001
        
        Proveedor: Suministros XYZ S.L.
        ID Proveedor: PROV-456
        
        Artículos:
        1. Papel de oficina - Código: PAP-001
           Cantidad: 100 unidades a 5,00 € cada una = 500,00 €
        
        2. Tinta para impresora - Código: TINT-002
           Cantidad: 20 unidades a 35,00 € cada una = 700,00 €
        
        Subtotal: 1 200,00 €
        IVA (21%): 252,00 €
        Total: 1 452,00 €
        
        Términos de pago: Neto 30 días
        Moneda: EUR
        """
        
        german_invoice = """
        RECHNUNG
        
        Rechnungsnummer: RE-2024-DE-555
        Datum: 12. Dezember 2024
        
        Rechnungsempfänger:
        Firma ABC GmbH
        Hauptstraße 789
        Berlin, 10115
        
        Lieferant: Bürobedarf XYZ AG
        Lieferanten-ID: LIEF-321
        
        Artikel:
        1. Schreibwaren - Artikelnummer: SCHREIB-001
           Menge: 30 Stück à 8,00 € = 240,00 €
        
        2. Druckerpapier - Artikelnummer: PAPIER-002
           Menge: 50 Stück à 12,00 € = 600,00 €
        
        Zwischensumme: 840,00 €
        MwSt (19%): 159,60 €
        Gesamtbetrag: 999,60 €
        
        Zahlungsbedingungen: 14 Tage netto
        Währung: EUR
        """
        
        test_cases = [
            ("French", french_invoice, "test-translation-fr-001"),
            ("Spanish", spanish_invoice, "test-translation-es-002"),
            ("German", german_invoice, "test-translation-de-003")
        ]
        
        translation_results = []
        
        for language, invoice_text, ctx_id in test_cases:
            print("="*70)
            print(f"TEST: Translate {language} Invoice to Structured English Data")
            print("="*70)
            print(f"Input language: {language}")
            print(f"Input text length: {len(invoice_text)} characters\n")
            
            test_inputs = {
                "context_id": ctx_id,
                "raw_text": invoice_text
            }
            
            response = await agent.process_async(test_inputs)
            
            print(f"Message Type: {response.message_type}")
            print(f"Source Agent: {response.source_agent}")
            print(f"Target Agent: {response.target_agent}")
            print(f"Context ID: {response.context_id}")
            
            if response.message_type == "TASK_HANDOFF":
                extracted = response.payload.get("extracted_data", {})
                print(f"\nTranslated & Extracted Data (English):")
                print(f"  Invoice Number: {extracted.get('invoice_no')}")
                print(f"  Invoice Date: {extracted.get('invoice_date')}")
                print(f"  Vendor ID: {extracted.get('vendor_id')}")
                print(f"  Total Amount: {extracted.get('total_amount')}")
                print(f"  Currency: {extracted.get('currency')}")
                print(f"  Payment Terms: {extracted.get('payment_terms', 'N/A')}")
                
                line_items = extracted.get('line_items', [])
                print(f"  Line Items: {len(line_items)}")
                
                if line_items:
                    print(f"\n  Line Items Detail (Translated to English):")
                    for i, item in enumerate(line_items, 1):
                        print(f"    {i}. Item Code: {item.get('item_code')}")
                        print(f"       Description: {item.get('description')}")
                        print(f"       Quantity: {item.get('quantity')}")
                        print(f"       Unit Price: {item.get('unit_price')}")
                        print(f"       Total: {item.get('total')}")
                
                translation_results.append({
                    "language": language,
                    "success": True,
                    "extracted_data": extracted
                })
            else:
                print(f"\nError: {response.payload.get('error')}")
                translation_results.append({
                    "language": language,
                    "success": False,
                    "error": response.payload.get('error')
                })
            
            print()
        
        print("="*70)
        print("TEST: Handle Missing Text")
        print("="*70)
        
        empty_inputs = {"context_id": "test-translation-empty"}
        response_empty = await agent.process_async(empty_inputs)
        
        print(f"Message Type: {response_empty.message_type}")
        print(f"Target Agent: {response_empty.target_agent}")
        print(f"Error: {response_empty.payload.get('error')}")
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        
        print("\nTranslation Summary:")
        successful = sum(1 for r in translation_results if r['success'])
        print(f"  Total tests: {len(translation_results)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {len(translation_results) - successful}")
        
        for result in translation_results:
            if result['success']:
                status = "SUCCESS"
                print(f"  - {result['language']} invoice: {status}")
                extracted = result['extracted_data']
                print(f"    Invoice: {extracted.get('invoice_no')}, Amount: {extracted.get('total_amount')} {extracted.get('currency')}")
            else:
                print(f"  - {result['language']} invoice: FAILED - {result.get('error')}")
        
        print("\nNOTE: All foreign language content should be translated to English")
        print("      in the structured output. Verify descriptions are in English.")
    
    try:
        asyncio.run(test_agent())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during testing: {e}")
        import traceback
        traceback.print_exc()