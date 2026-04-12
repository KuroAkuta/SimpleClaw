"""
Subagent task endpoints for monitoring and controlling subagent tasks.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from subagent.executor import (
    get_background_task_result,
    list_background_tasks,
    request_cancel_background_task,
    cleanup_background_task,
    get_subagent_tool_history,
    SubagentStatus,
)

subagent_router = APIRouter(prefix="/api/subagent")


class SubagentTaskStatusResponse(BaseModel):
    """Response model for subagent task status."""
    task_id: str
    status: str
    result: str | None = None
    error: str | None = None
    turns: int | None = None
    elapsed_time: float | None = None


@subagent_router.get("/task/{task_id}/status")
async def get_subagent_task_status(task_id: str):
    """
    Get the status of a subagent task.

    Args:
        task_id: The task ID to check

    Returns:
        SubagentTaskStatusResponse with current status
    """
    result = get_background_task_result(task_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # Calculate elapsed time
    elapsed_time = None
    if result.started_at:
        from datetime import datetime
        end_time = result.completed_at or datetime.now()
        elapsed_time = (end_time - result.started_at).total_seconds()

    # Map internal status to string
    status_map = {
        SubagentStatus.PENDING: "pending",
        SubagentStatus.RUNNING: "running",
        SubagentStatus.COMPLETED: "completed",
        SubagentStatus.FAILED: "failed",
        SubagentStatus.CANCELLED: "cancelled",
        SubagentStatus.TIMED_OUT: "timed_out",
    }

    return SubagentTaskStatusResponse(
        task_id=result.task_id,
        status=status_map.get(result.status, "unknown"),
        result=result.result,
        error=result.error,
        elapsed_time=elapsed_time,
    )


@subagent_router.get("/tasks")
async def list_subagent_tasks():
    """
    List all subagent tasks.

    Returns:
        List of task statuses
    """
    tasks = list_background_tasks()

    status_map = {
        SubagentStatus.PENDING: "pending",
        SubagentStatus.RUNNING: "running",
        SubagentStatus.COMPLETED: "completed",
        SubagentStatus.FAILED: "failed",
        SubagentStatus.CANCELLED: "cancelled",
        SubagentStatus.TIMED_OUT: "timed_out",
    }

    return [
        {
            "task_id": task.task_id,
            "status": status_map.get(task.status, "unknown"),
            "result": task.result,
            "error": task.error,
        }
        for task in tasks
    ]


@subagent_router.get("/task/{task_id}/tools")
async def get_subagent_task_tools(task_id: str):
    """
    Get the tool execution history for a subagent task.

    Args:
        task_id: The task ID to get tool history for

    Returns:
        List of tool execution events
    """
    history = get_subagent_tool_history(task_id)
    return {"task_id": task_id, "tools": history}


@subagent_router.post("/task/{task_id}/cancel")
async def cancel_subagent_task(task_id: str):
    """
    Cancel a running subagent task.

    Args:
        task_id: The task ID to cancel

    Returns:
        Success message
    """
    result = get_background_task_result(task_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # Only cancel running or pending tasks
    if result.status not in [SubagentStatus.PENDING, SubagentStatus.RUNNING]:
        return {"success": False, "message": f"Task is not running (status: {result.status.value})"}

    request_cancel_background_task(task_id)

    return {"success": True, "message": f"Cancellation requested for task '{task_id}'"}


@subagent_router.delete("/task/{task_id}")
async def cleanup_subagent_task(task_id: str):
    """
    Clean up a completed subagent task.

    Args:
        task_id: The task ID to clean up

    Returns:
        Success message
    """
    cleanup_background_task(task_id)
    return {"success": True, "message": f"Task '{task_id}' cleaned up"}
