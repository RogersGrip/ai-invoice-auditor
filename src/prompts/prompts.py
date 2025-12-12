TRANSLATION_PROMPT = """You are an expert invoice data extraction and translation system.

TASK:
1. TRANSLATE all non-English content to ENGLISH
2. Extract structured invoice data
3. ALL text fields MUST be in English (descriptions, vendor names, payment terms, etc.)

CRITICAL TRANSLATION RULES:
- Translate ALL foreign language text to English equivalents
- Item descriptions: Convert to English (e.g., "Fournitures de bureau" -> "Office Supplies")
- Vendor names: Translate descriptive parts (e.g., "XYZ Fournitures SARL" -> "XYZ Supplies SARL")
- Payment terms: Translate (e.g., "30 jours nets" -> "Net 30 days", "14 Tage netto" -> "Net 14 days")
- Addresses: Translate street types (e.g., "Rue des Affaires" -> "Business Street")
- Keep unchanged: Invoice numbers, item codes, numeric values, currency codes (EUR, USD, etc.)

EXAMPLES:
- French: "Équipement informatique" -> "Computer Equipment"
- Spanish: "Papel de oficina" -> "Office Paper"
- German: "Schreibwaren" -> "Stationery"
- French: "Facturé à" -> Extract as customer info (translate if needed)
- Spanish: "Términos de pago: Neto 30 días" -> "Payment Terms: Net 30 days"

{format_instructions}

INVOICE TEXT (may be in any language - French, Spanish, German, Italian, etc.):
{text}

OUTPUT REQUIREMENTS:
- Return valid JSON following the schema
- ALL text fields must be in ENGLISH
- Preserve all numeric values exactly as shown
- Keep currency codes (EUR, USD, GBP) unchanged
- Translate dates to standard format (YYYY-MM-DD)

Extract and translate now:"""