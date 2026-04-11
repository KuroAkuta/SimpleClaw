# Tools package for the Simple Agent

from .basic_tools import (
    run_command,
    read_file,
    write_file,
    list_directory,
    find_files,
    get_skill,
    execute_skill_script,
)
from .memory_tools import save_memory, load_memory, clear_memory

__all__ = [
    'run_command',
    'read_file',
    'write_file',
    'list_directory',
    'find_files',
    'get_skill',
    'execute_skill_script',
    'save_memory',
    'load_memory',
    'clear_memory',
    'get_all_tools',
]


def get_all_tools():
    """Get all available tools."""
    return [
        # Bash
        run_command,
        # File operations
        read_file,
        write_file,
        list_directory,
        find_files,
        # Skill system
        get_skill,
        execute_skill_script,
        # Memory tools
        save_memory,
        load_memory,
        clear_memory,
    ]
