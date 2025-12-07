import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Python Path: {sys.path}")

try:
    import langfuse
    print(f"Langfuse Location: {langfuse.__file__}")
    print(f"Langfuse Version: {langfuse.version.__version__}")
    print(f"Langfuse Dir: {dir(langfuse)}")
except ImportError as e:
    print(f"Failed to import langfuse: {e}")
    sys.exit(1)

try:
    import langfuse.decorators
    print("Successfully imported langfuse.decorators")
except ImportError as e:
    print(f"Failed to import langfuse.decorators: {e}")
    
    # List files in langfuse dir
    import os
    lf_dir = os.path.dirname(langfuse.__file__)
    print(f"Contents of {lf_dir}:")
    for f in os.listdir(lf_dir):
        print(f" - {f}")
