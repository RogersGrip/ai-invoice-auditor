import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from langchain_core.runnables.graph import Graph
from loguru import logger

console = Console()

def visualize_graph(workflow_app, output_path="docs/workflow_graph.png"):
    """Generates a PNG visualization of the LangGraph workflow."""
    try:
        graph: Graph = workflow_app.get_graph()
        png_data = graph.draw_mermaid_png()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(png_data)
        logger.info(f"Workflow visualization saved to: {output_path}")
    except Exception as e:
        logger.warning(f"Could not generate graph visualization (Graphviz required?): {e}")

def print_hitl_analysis(step_name: str, data: dict, logs: list[str]):
    """
    Prints a rich HITL analysis table to the console.
    This simulates the data review step before approval.
    """
    table = Table(title=f"🔎 HITL Analysis: {step_name}", show_header=True, header_style="bold magenta")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    # Add Data
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = str(v)[:100] + "..." # Truncate complex objects
        table.add_row(str(k), str(v))
    
    # Add Logs
    log_content = "\n".join(logs[-5:]) if logs else "No recent logs"
    
    console.print(Panel(table, expand=False))
    console.print(Panel(log_content, title="Recent System Logs", style="yellow"))
    console.print("[bold red]Action Required:[/bold red] awaiting approval...")