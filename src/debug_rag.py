import sys
import os
from src.database.qdrant_db import vector_store
from src.core.config import settings

# Force re-init if needed
vector_store._init_db()

query = "globallogistics"
print(f"--- Debugging RAG for query: '{query}' ---")

# 1. Check Collection Info
client = vector_store._get_client()
try:
    info = client.get_collection(vector_store.collection_name)
    print(f"Collection '{vector_store.collection_name}' status: {info.status}")
    # Use points_count as vectors_count might be deprecated/missing
    print(f"Points count: {info.points_count}")
except Exception as e:
    print(f"Collection Error: {e}")

# 2. Perform Search
results = vector_store.search(query, limit=5)
print(f"\nSearch Results ({len(results)}):")
for r in results:
    print(f"Score: {r['score']:.4f}")
    print(f"Text Snippet: {r['text'][:100]}...")
    print(f"Metadata: {r['metadata']}")

if not results:
    print("\nNo results found. Indexing might have failed or embeddings are misaligned.")
