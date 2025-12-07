from litellm import embedding
import sys

try:
    print("Testing embedding...")
    response = embedding(
        model="ollama/nomic-embed-text",
        input=["Hello world"]
    )
    print("Success!")
    print(f"Embedding length: {len(response.data[0]['embedding'])}")
except Exception as e:
    print(f"Failed: {e}")
    sys.exit(1)
