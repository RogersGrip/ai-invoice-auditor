import httpx
import asyncio
import json

async def test_agent():
    url = "http://localhost:8001/translate"
    
    print(f"--- Testing Translation Agent at {url} ---")

    # 1. Define the Payload (Matches TranslationRequest schema)
    payload = {
        "raw_text": """
        RECHNUNG
        Nr: INV-2024-001
        Datum: 2024-05-01
        
        Positionen:
        1. Beratung (Consulting) - 10 Std - 100 EUR/Std - 1000 EUR
        2. Reisekosten - 1 Pauschale - 50 EUR - 50 EUR
        
        Gesamtbetrag: 1050 EUR
        """,
        "metadata": {
            "sender": "invoice@consulting-gmbh.de",
            "language": "de",
            "subject": "Invoice for May Services"
        },
        "target_language": "English"
    }
    
    # 2. Send Request
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            
            if resp.status_code == 200:
                print("\nSUCCESS! Response received:")
                data = resp.json()
                
                # Pretty print the JSON output
                print(json.dumps(data, indent=2))
                
                # Basic validation check
                if data.get('structured_data'):
                    print("\n✅ Structured Data extracted successfully.")
            else:
                print(f"\nFAILED: {resp.status_code}")
                print(resp.text)
                
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        print("Make sure the agent is running: 'uv run python src/adk_agents/translator/main.py'")

if __name__ == "__main__":
    asyncio.run(test_agent())