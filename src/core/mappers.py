import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from src.core.protocol import (
    Task, TaskStatus, TaskState, Artifact, Part, DataPart, FilePart
)
from src.core.state import InvoiceState, ProcessingStatus

def map_status_to_state(status: ProcessingStatus) -> TaskState:
    mapping = {
        ProcessingStatus.PENDING: TaskState.SUBMITTED,
        ProcessingStatus.EXTRACTED: TaskState.WORKING,
        ProcessingStatus.TRANSLATED: TaskState.WORKING,
        ProcessingStatus.VALIDATED: TaskState.WORKING,
        ProcessingStatus.COMPLETED: TaskState.COMPLETED,
        ProcessingStatus.FAILED: TaskState.FAILED,
        ProcessingStatus.DATA_INVALID: TaskState.FAILED,
        ProcessingStatus.FLAGGED: TaskState.COMPLETED
    }
    return mapping.get(status, TaskState.UNSPECIFIED)

def map_state_to_task(state: InvoiceState, context_id: str) -> Task:
    artifacts: List[Artifact] = []

    if state.extracted_data:
        artifacts.append(Artifact(
            artifactId=f"art_data_{state.file_name}",
            name="Extracted Invoice Data",
            description="JSON structure of the invoice",
            parts=[Part(data=DataPart(data=state.extracted_data))]
        ))

    if state.report_path:
        for fmt, path in state.report_path.items():
            artifacts.append(Artifact(
                artifactId=f"art_report_{fmt}_{state.file_name}",
                name=f"Validation Report ({fmt.upper()})",
                description=f"Final audit report in {fmt}",
                parts=[Part(file=FilePart(
                    mediaType="application/pdf" if fmt == "pdf" else "application/json",
                    name=f"{state.file_name}_report.{fmt}",
                    fileWithUri=str(path)
                ))]
            ))

    a2a_state = map_status_to_state(state.status)
    
    return Task(
        id=state.file_name,
        contextId=context_id,
        status=TaskStatus(
            state=a2a_state,
            timestamp=datetime.now(timezone.utc).isoformat()
        ),
        artifacts=artifacts if artifacts else None,
        metadata={
            "original_file": state.file_path,
            "current_node": state.current_step,
            "validation_valid": state.validation_results.get("is_valid")
        }
    )