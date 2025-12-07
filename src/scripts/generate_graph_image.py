import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.workflows.graph import create_invoice_graph

def generate_graph_image():
    print(">>> Generating Graph Image...")
    try:
        app = create_invoice_graph()
        
        # Get Mermaid PNG
        png_data = app.get_graph().draw_mermaid_png()
        
        output_path = "artifacts/invoice_workflow.png"
        os.makedirs("artifacts", exist_ok=True)
        
        with open(output_path, "wb") as f:
            f.write(png_data)
            
        print(f">>> Graph image saved to: {output_path}")
        return True
    except Exception as e:
        print(f"!!! Failed to generate graph image: {e}")
        return False

if __name__ == "__main__":
    generate_graph_image()
