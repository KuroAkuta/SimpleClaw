"""Subagent system for delegating complex tasks.

This module provides a subagent system similar to Claude Code's subagent architecture:
- SubagentConfig: Configuration dataclass for defining subagent behavior
- SubagentExecutor: Engine for running subagents with isolated context
- Built-in subagents: general-purpose, bash

Usage:
    from subagent import get_subagent_tools, get_subagent_tool_descriptions

    # Add to system prompt
    system_prompt += get_subagent_tool_descriptions()

    # Get tools
    tools = get_subagent_tools()
"""

from subagent.config import SubagentConfig
from subagent.executor import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    get_background_task_result,
    list_background_tasks,
    cleanup_background_task,
    request_cancel_background_task,
    MAX_CONCURRENT_SUBAGENTS,
    get_subagent_tool_history,
)
from subagent.registry import (
    get_subagent_config,
    list_subagents,
    get_subagent_names,
)
from subagent.builtins import BUILTIN_SUBAGENTS
from subagent.tools import (
    task,
    task_async,
    get_task_result,
    list_task_status,
    get_subagent_tool_descriptions,
    get_all_subagent_tools,
)

__all__ = [
    # Config
    "SubagentConfig",
    # Executor
    "SubagentExecutor",
    "SubagentResult",
    "SubagentStatus",
    "get_background_task_result",
    "list_background_tasks",
    "cleanup_background_task",
    "request_cancel_background_task",
    "get_subagent_tool_history",
    "MAX_CONCURRENT_SUBAGENTS",
    # Registry
    "get_subagent_config",
    "list_subagents",
    "get_subagent_names",
    # Built-ins
    "BUILTIN_SUBAGENTS",
    # Tools
    "task",
    "task_async",
    "get_task_result",
    "list_task_status",
    "get_subagent_tool_descriptions",
    "get_all_subagent_tools",
]
