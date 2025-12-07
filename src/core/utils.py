from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Dict, Any, List
import os
from pathlib import Path

console = Console()

def find_project_root(current_path: str | Path = ".") -> Path:
    """
    Finds the project root by looking for pyproject.toml
    """
    current_path = Path(current_path).resolve()
    for parent in [current_path] + list(current_path.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(os.getcwd()) # Fallback

def print_hitl_analysis(step_name: str, data: Dict[str, Any] | Any, discrepancies: List[str] = []) -> None:
    """
    Renders a Rich table analysis for Human-In-The-Loop review.
    """
    console.print(Panel(f"[bold cyan]HITL Analysis: {step_name}[/bold cyan]", expand=False))
    
    # 1. Mismatch / Discrepancy Table
    if discrepancies:
        table = Table(title="⚠ Discrepancies Found", style="red")
        table.add_column("Issue", style="red")
        for d in discrepancies:
            table.add_row(d)
        console.print(table)
    else:
        console.print("[bold green]✔ No Discrepancies Found[/bold green]")
        
    # 2. Data Snapshot
    if data:
        console.print("\n[bold]Current Data Snapshot:[/bold]")
        # If data is Pydantic model dump
        if isinstance(data, dict):
            # Print key fields
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Field")
            table.add_column("Value")
            
            # Smart filter for display
            keys_to_show = ['invoice_no', 'invoice_date', 'total_amount', 'currency', 'vendor_id', 'is_valid']
            for k, v in data.items():
                if k in keys_to_show or k.startswith('is_'):
                    table.add_row(k, str(v))
            
            if len(table.rows) > 0:
                console.print(table)
            else:
                 console.print(str(data)[:500]) # Fallback
        else:
             console.print(str(data)[:500])

    console.print("\n" + "-"*40 + "\n")