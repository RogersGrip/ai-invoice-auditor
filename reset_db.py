from src.database.qdrant_db import VectorDB
from src.core.logger import logger
from qdrant_client import QdrantClient
from src.core.config import settings
import shutil

def reset_db():
    print("WARNING: This will wipe the entire Vector Database.")
    confirm = input("Type 'yes' to continue: ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        return

    try:
        # Use simple client to delete collection
        client = QdrantClient(path=str(settings.QDRANT_PATH))
        if client.collection_exists("invoices"):
            client.delete_collection("invoices")
            print("Collection 'invoices' deleted.")
        else:
            print("Collection 'invoices' did not exist.")
        client.close()
        
        # Optional: Checking file system
        # shutil.rmtree(settings.QDRANT_PATH, ignore_errors=True)
        
        print("Re-initializing DB...")
        db = VectorDB()
        db._init_db()
        print("Database reset successfully! All previous index data is gone.")
        
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_db()
