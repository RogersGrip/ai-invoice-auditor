import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from a2a.types import Task, TaskStatus, TaskState, Artifact, Part, DataPart, FilePart
from src.core.state import InvoiceState, ProcessingStatus


def map_status_to_state(status: ProcessingStatus) -> TaskState:
    """
    Map internal ProcessingStatus to A2A TaskState.
    
    Args:
        status: The internal processing status
        
    Returns:
        The corresponding A2A TaskState
    """
    mapping = {
        ProcessingStatus.PENDING: TaskState.submitted,
        ProcessingStatus.EXTRACTED: TaskState.working,
        ProcessingStatus.TRANSLATED: TaskState.working,
        ProcessingStatus.VALIDATED: TaskState.working,
        ProcessingStatus.COMPLETED: TaskState.completed,
        ProcessingStatus.FAILED: TaskState.failed,
        ProcessingStatus.DATA_INVALID: TaskState.failed,
        ProcessingStatus.FLAGGED: TaskState.completed
    }
    return mapping.get(status, TaskState.unknown)


def map_state_to_task(state: InvoiceState, context_id: str) -> Task:
    """
    Convert an InvoiceState to an A2A Task representation.
    
    Args:
        state: The invoice state to convert
        context_id: The context identifier for the task
        
    Returns:
        An A2A Task object representing the invoice state
    """
    artifacts: List[Artifact] = []

    # Add extracted data artifact if available
    if state.extracted_data:
        artifacts.append(Artifact(
            artifact_id=f"art_data_{state.file_name}",
            name="Extracted Invoice Data",
            description="JSON structure of the invoice",
            parts=[Part(data=DataPart(data=state.extracted_data))]
        ))

    # Add report artifacts if available
    if state.report_path:
        for fmt, path in state.report_path.items():
            # Determine media type based on format
            media_type = "application/pdf" if fmt == "pdf" else "application/json"
            
            artifacts.append(Artifact(
                artifact_id=f"art_report_{fmt}_{state.file_name}",
                name=f"Validation Report ({fmt.upper()})",
                description=f"Final audit report in {fmt}",
                parts=[Part(file=FilePart(
                    media_type=media_type,
                    name=f"{state.file_name}_report.{fmt}",
                    file_with_uri=str(path)
                ))]
            ))

    # Map internal status to A2A state
    a2a_state = map_status_to_state(state.status)
    
    # Create and return the Task
    return Task(
        id=state.file_name,
        context_id=context_id,
        status=TaskStatus(
            state=a2a_state,
            timestamp=datetime.now(timezone.utc).isoformat()
        ),
        artifacts=artifacts if artifacts else None,
        metadata={
            "original_file": state.file_path,
            "current_node": state.current_step,
            "validation_valid": state.validation_results.get("is_valid") if state.validation_results else None
        }
    )


def batch_map_states_to_tasks(
    states: List[InvoiceState], 
    context_id: str
) -> List[Task]:
    """
    Convert multiple InvoiceStates to A2A Tasks.
    
    Args:
        states: List of invoice states to convert
        context_id: The context identifier for all tasks
        
    Returns:
        List of A2A Task objects
    """
    return [map_state_to_task(state, context_id) for state in states]


def get_task_summary(task: Task) -> Dict[str, Any]:
    """
    Generate a summary of a Task for logging or display purposes.
    
    Args:
        task: The task to summarize
        
    Returns:
        A dictionary containing the task summary
    """
    return {
        "task_id": task.id,
        "context_id": task.context_id,
        "state": task.status.state.value if task.status else "unknown",
        "timestamp": task.status.timestamp if task.status else None,
        "artifact_count": len(task.artifacts) if task.artifacts else 0,
        "metadata": task.metadata
    }