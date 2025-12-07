import sys
import os
sys.path.append(os.getcwd())
from src.mcp_server.erp import mcp

print("Scanning attributes...")
for attr in dir(mcp):
    if "tool" in attr or "registry" in attr or "func" in attr:
        print(f"Candidate: {attr}")
        try:
            val = getattr(mcp, attr)
            print(f"  Type: {type(val)}")
            if isinstance(val, dict):
                print(f"  Keys: {list(val.keys())}")
            if isinstance(val, list):
                print(f"  Len: {len(val)}")
        except:
            pass
