"""Subagent registry for managing available subagents."""

import logging
from dataclasses import replace

from subagent.builtins import BUILTIN_SUBAGENTS
from subagent.config import SubagentConfig

logger = logging.getLogger(__name__)


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get a subagent configuration by name.

    Args:
        name: The name of the subagent.

    Returns:
        SubagentConfig if found, None otherwise.
    """
    return BUILTIN_SUBAGENTS.get(name)


def list_subagents() -> list[SubagentConfig]:
    """List all available subagent configurations.

    Returns:
        List of all registered SubagentConfig instances.
    """
    return list(BUILTIN_SUBAGENTS.values())


def get_subagent_names() -> list[str]:
    """Get all available subagent names.

    Returns:
        List of subagent names.
    """
    return list(BUILTIN_SUBAGENTS.keys())
