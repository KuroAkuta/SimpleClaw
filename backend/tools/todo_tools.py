"""
TodoList management tools for complex task tracking.

This module provides tools for creating, updating, and managing todo lists
during agent sessions. The AI can use these tools to track progress on
complex multi-step tasks.
"""

import logging
from typing import Annotated, Literal
from langchain.tools import tool

logger = logging.getLogger(__name__)

# In-memory storage for todos (per-thread in the future)
# Format: {thread_id: [{"content": str, "status": str}]}
_todos_store: dict[str, list[dict]] = {}


def get_todos_for_thread(thread_id: str) -> list[dict]:
    """Get todos for a specific thread."""
    return _todos_store.get(thread_id, [])


def set_todos_for_thread(thread_id: str, todos: list[dict]) -> None:
    """Set todos for a specific thread."""
    _todos_store[thread_id] = todos


def clear_todos_for_thread(thread_id: str) -> None:
    """Clear todos for a specific thread."""
    if thread_id in _todos_store:
        del _todos_store[thread_id]


@tool
def write_todos(
    todos: Annotated[
        list[dict],
        "List of todo items. Each item is a dict with 'content' (str) and 'status' (str: 'pending', 'in_progress', or 'completed') keys."
    ],
    thread_id: Annotated[
        str,
        "The thread/session ID to associate these todos with"
    ] = "default",
) -> str:
    """
    Write or update the todo list for tracking complex tasks.

    **CRITICAL: Only use this tool for complex tasks (3+ steps). For simple requests, just do the work directly.**

    Use this tool in these scenarios:
    1. **Complex multi-step tasks**: When a task requires 3 or more distinct steps
    2. **Non-trivial tasks**: Tasks requiring careful planning or multiple operations
    3. **User explicitly requests todo list**: When the user directly asks you to track tasks
    4. **Multiple tasks**: When users provide a list of things to be done
    5. **Dynamic planning**: When the plan may need updates based on intermediate results

    Skip this tool when:
    1. The task is straightforward and takes less than 3 steps
    2. The task is trivial and tracking provides no benefit
    3. The task is purely conversational or informational
    4. It's clear what needs to be done and you can just do it

    Args:
        todos: List of todo items. Each item should have:
            - content (str): Description of the task
            - status (str): One of 'pending', 'in_progress', or 'completed'
        thread_id: Optional thread ID for multi-thread support (default: "default")

    Returns:
        A formatted string showing the current todo list with status

    Examples:
        # Create a new todo list with first task in progress
        write_todos([
            {"content": "Analyze the codebase structure", "status": "in_progress"},
            {"content": "Identify the bug location", "status": "pending"},
            {"content": "Fix the bug", "status": "pending"},
            {"content": "Test the fix", "status": "pending"}
        ])

        # Update an existing todo list (mark completed, start next)
        write_todos([
            {"content": "Analyze the codebase structure", "status": "completed"},
            {"content": "Identify the bug location", "status": "in_progress"},
            {"content": "Fix the bug", "status": "pending"},
            {"content": "Test the fix", "status": "pending"}
        ])
    """
    # Validate todos
    if not todos:
        return "Error: Todo list cannot be empty"

    valid_statuses = {"pending", "in_progress", "completed"}
    validated_todos = []

    for i, todo in enumerate(todos):
        if not isinstance(todo, dict):
            return f"Error: Todo item {i} is not a dictionary"
        if "content" not in todo:
            return f"Error: Todo item {i} missing 'content' field"
        if "status" not in todo:
            return f"Error: Todo item {i} missing 'status' field"
        if todo["status"] not in valid_statuses:
            return f"Error: Todo item {i} has invalid status '{todo['status']}'. Must be one of: {valid_statuses}"

        validated_todos.append({
            "content": str(todo["content"]),
            "status": todo["status"],
        })

    # Store the todos
    set_todos_for_thread(thread_id, validated_todos)

    # Format the response - return JSON structure for frontend parsing
    import json
    response_data = {
        "todos": validated_todos,
        "formatted": _format_todos(validated_todos)
    }
    result = json.dumps(response_data, ensure_ascii=False)
    print(f"[DEBUG] write_todos returning: {result[:100]}...")
    return result


def _format_todos(todos: list[dict]) -> str:
    """Format a list of todos into a human-readable string."""
    if not todos:
        return "No todos in the list."

    lines = ["Current Todo List:"]
    for i, todo in enumerate(todos, 1):
        status_icon = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
        }.get(todo["status"], "❓")

        lines.append(f"  {i}. {status_icon} [{todo['status']}] {todo['content']}")

    # Summary
    pending = sum(1 for t in todos if t["status"] == "pending")
    in_progress = sum(1 for t in todos if t["status"] == "in_progress")
    completed = sum(1 for t in todos if t["status"] == "completed")

    lines.append(f"\nSummary: {completed} completed, {in_progress} in progress, {pending} pending")

    return "\n".join(lines)


@tool
def get_todos(
    thread_id: Annotated[
        str,
        "The thread/session ID to get todos for"
    ] = "default",
) -> str:
    """
    Get the current todo list for a thread.

    Args:
        thread_id: Optional thread ID (default: "default")

    Returns:
        Formatted todo list string
    """
    todos = get_todos_for_thread(thread_id)
    return _format_todos(todos)


@tool
def clear_todos(
    thread_id: Annotated[
        str,
        "The thread/session ID to clear todos for"
    ] = "default",
) -> str:
    """
    Clear the todo list for a thread.

    Args:
        thread_id: Optional thread ID (default: "default")

    Returns:
        Confirmation message
    """
    clear_todos_for_thread(thread_id)
    return "Todo list cleared."


def get_all_todo_tools():
    """Get all todo-related tools."""
    return [write_todos, get_todos, clear_todos]
