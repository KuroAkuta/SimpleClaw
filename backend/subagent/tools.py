"""Subagent delegation tool."""

import logging
import time
from typing import Annotated

from langchain.tools import tool

from subagent.builtins import BUILTIN_SUBAGENTS
from subagent.config import SubagentConfig
from subagent.executor import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    get_background_task_result,
    list_background_tasks,
    cleanup_background_task,
    MAX_CONCURRENT_SUBAGENTS,
)
from subagent.registry import get_subagent_config, get_subagent_names

logger = logging.getLogger(__name__)


def _get_available_tools():
    """Get all available tools for subagent execution."""
    from tools.basic_tools import get_all_tools
    return get_all_tools()


def _get_subagent_type_description() -> str:
    """Get description of available subagent types."""
    return "Available options: " + ", ".join(get_subagent_names())


@tool
def task(
    description: str = "Subagent task",
    prompt: str = "",
    subagent_type: Annotated[
        str,
        _get_subagent_type_description()
    ] = "general-purpose",
    max_turns: Annotated[
        int,
        "Maximum number of turns the subagent can take (default: 50)"
    ] = 50,
) -> str:
    """
    Delegate a complex task to a specialized subagent.

    Use this tool when:
    - The task requires multiple steps and would benefit from isolated context
    - You want to delegate to a specialist agent (e.g., bash expert)
    - The task is well-defined and can be executed autonomously

    Args:
        description: A brief description of the task (for your reference)
        prompt: The detailed task description to give to the subagent
        subagent_type: The type of subagent to use (default: general-purpose)
        max_turns: Maximum number of turns for the subagent (default: 50)

    Returns:
        The subagent's result message
    """
    # Get subagent config
    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(get_subagent_names())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    # Override max_turns if specified (ensure int conversion)
    try:
        max_turns_int = int(max_turns) if max_turns != 50 else 50
    except (ValueError, TypeError):
        max_turns_int = 50

    if max_turns_int != 50:
        from dataclasses import replace
        config = replace(config, max_turns=max_turns_int)

    # Get all available tools
    all_tools = _get_available_tools()

    # Create executor
    executor = SubagentExecutor(
        config=config,
        tools=all_tools,
    )

    logger.info(f"Delegating task to {subagent_type} subagent: {description}")

    # Execute synchronously
    result = executor.execute(prompt)

    # Log and return result
    print(f"[DEBUG] Subagent execution result:")
    print(f"  - Status: {result.status}")
    print(f"  - Result: {result.result[:200] if result.result else 'None'}...")
    print(f"  - Messages: {len(result.messages) if result.messages else 0}")

    if result.status == SubagentStatus.COMPLETED:
        logger.info(f"Subagent completed: {result.result[:100] if len(result.result or '') > 100 else result.result}")
        return result.result or "Task completed with no output"
    elif result.status == SubagentStatus.FAILED:
        logger.error(f"Subagent failed: {result.error}")
        return f"Task failed: {result.error}"
    elif result.status == SubagentStatus.TIMED_OUT:
        logger.error(f"Subagent timed out: {result.error}")
        return f"Task timed out: {result.error}"
    elif result.status == SubagentStatus.CANCELLED:
        return "Task was cancelled by user"
    else:
        return f"Unexpected status: {result.status}"


# For async usage (advanced - only use for long-running tasks)
@tool
def task_async(
    description: str = "Subagent task",
    prompt: str = "",
    subagent_type: str = "general-purpose",
    max_turns: int = 50,
    task_id: str = None,  # Optional task ID for tracking
) -> str:
    """
    Delegate a task to a subagent asynchronously (non-blocking).

    This tool starts the subagent in the background and returns immediately
    with a task ID. Use get_task_result to retrieve the result.

    Args:
        description: A brief description of the task
        prompt: The detailed task description for the subagent
        subagent_type: The type of subagent to use
        max_turns: Maximum number of turns for the subagent
        task_id: Optional task ID for tracking (if not provided, auto-generated)

    Returns:
        Task ID for tracking progress
    """
    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(BUILTIN_SUBAGENTS.keys())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    from dataclasses import replace
    try:
        max_turns_int = int(max_turns)
    except (ValueError, TypeError):
        max_turns_int = 50

    if max_turns_int != 50:
        config = replace(config, max_turns=max_turns_int)

    all_tools = _get_available_tools()
    executor = SubagentExecutor(config=config, tools=all_tools)

    task_id = executor.execute_async(prompt, task_id=task_id)
    return f"Task started. Task ID: {task_id}. Use get_task_result with this ID to check status."


@tool
def get_task_result(task_id: str) -> str:
    """
    Get the result of an asynchronously running subagent task.

    Args:
        task_id: The task ID returned by task_async

    Returns:
        Task status and result (if completed)
    """
    result = get_background_task_result(task_id)

    if result is None:
        return f"Error: Task '{task_id}' not found"

    if result.status == SubagentStatus.PENDING:
        return f"Task '{task_id}' is pending..."
    elif result.status == SubagentStatus.RUNNING:
        return f"Task '{task_id}' is still running..."
    elif result.status == SubagentStatus.COMPLETED:
        output = f"Task '{task_id}' completed:\n{result.result}"
        # Clean up after retrieving result
        cleanup_background_task(task_id)
        return output
    elif result.status == SubagentStatus.FAILED:
        output = f"Task '{task_id}' failed: {result.error}"
        cleanup_background_task(task_id)
        return output
    elif result.status == SubagentStatus.TIMED_OUT:
        output = f"Task '{task_id}' timed out: {result.error}"
        cleanup_background_task(task_id)
        return output
    elif result.status == SubagentStatus.CANCELLED:
        return f"Task '{task_id}' was cancelled"
    else:
        return f"Task '{task_id}' has unknown status: {result.status}"


@tool
def list_task_status() -> str:
    """
    List all background subagent tasks and their statuses.

    Returns:
        Formatted list of tasks with their statuses
    """
    tasks = list_background_tasks()

    if not tasks:
        return "No background tasks found."

    lines = ["Background subagent tasks:"]
    for task in tasks:
        status_icon = {
            SubagentStatus.PENDING: "⏳",
            SubagentStatus.RUNNING: "🔄",
            SubagentStatus.COMPLETED: "✅",
            SubagentStatus.FAILED: "❌",
            SubagentStatus.TIMED_OUT: "⏰",
            SubagentStatus.CANCELLED: "🚫",
        }.get(task.status, "❓")

        lines.append(f"  {status_icon} {task.task_id}: {task.status.value}")
        if task.result:
            preview = task.result[:50] + "..." if len(task.result) > 50 else task.result
            lines.append(f"      Result: {preview}")
        if task.error:
            lines.append(f"      Error: {task.error}")

    return "\n".join(lines)


def get_subagent_tool_descriptions() -> str:
    """
    Get descriptions of available subagents for inclusion in system prompt.

    Returns:
        Formatted string with subagent names and descriptions
    """
    lines = ["<subagents>", "Available subagents for task delegation:"]

    for name, config in BUILTIN_SUBAGENTS.items():
        lines.append(f"\n### {name}")
        lines.append(config.description)

    lines.append("\nUsage: Call the 'task' tool with:")
    lines.append("- description: Brief task summary")
    lines.append("- prompt: Detailed instructions for the subagent")
    lines.append("- subagent_type: One of: " + ", ".join(BUILTIN_SUBAGENTS.keys()))
    lines.append("- max_turns: Optional limit on agent turns")
    lines.append("</subagents>")

    return "\n".join(lines)


def get_all_subagent_tools():
    """Get all subagent-related tools."""
    return [
        task,
        task_async,
        get_task_result,
        list_task_status,
    ]
