import sys
from pathlib import Path

# Add root to sys.path
root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root))

from qdrant_client import QdrantClient
from src.core.config import settings

def inspect_db():
    print(f"Connecting to Qdrant at: {settings.QDRANT_PATH}")
    client = QdrantClient(path=settings.QDRANT_PATH)
    
    try:
        info = client.get_collection("invoices")
        # Scroll through all points
        points, _ = client.scroll(
            collection_name="invoices",
            limit=100,
            with_payload=True,
            with_vectors=False
        )

        with open("debug_qdrant.log", "w", encoding="utf-8") as f:
            f.write(f"Collection Info: {info}\n")
            f.write(f"Found {len(points)} documents in DB:\n")
            
            found_target = False
            for p in points:
                fname = p.payload.get('filename', 'Unknown')
                text_snippet = p.payload.get('text', '')[:50].replace('\n', ' ')
                f.write(f"- ID: {p.id} | File: {fname} | Snippet: {text_snippet}...\n")
                
                if "INV_EN_002" in fname:
                    found_target = True
                    f.write(f"  >>> FOUND TARGET! Full Text: {p.payload.get('text')}\n")

            if not found_target:
                f.write("\n❌ CRITICAL: INV_EN_002.pdf is NOT in the database!\n")
            else:
                f.write("\n✅ INV_EN_002.pdf IS in the database!\n")
                
        print("Debug log written to debug_qdrant.log")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    inspect_db()
