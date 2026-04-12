"""Built-in subagent configurations."""

from pathlib import Path
from subagent.config import SubagentConfig

__all__ = [
    "GENERAL_PURPOSE_CONFIG",
    "BASH_AGENT_CONFIG",
]

# Get workspace and skills directories (same as main agent)
# __file__ is backend/subagent/builtins.py, so parent.parent = backend/
BACKEND_DIR = Path(__file__).parent.parent
WORKSPACE_DIR = BACKEND_DIR / "workspace"
SKILLS_DIR = BACKEND_DIR / ".agents" / "skills"

# =============================================================================
# General Purpose Subagent
# =============================================================================

GENERAL_PURPOSE_CONFIG = SubagentConfig(
    name="general-purpose",
    description="""A capable agent for complex, multi-step tasks that require both exploration and action.

Use this subagent when:
- The task requires both exploration and modification
- Complex reasoning is needed to interpret results
- Multiple dependent steps must be executed
- The task would benefit from isolated context management

Do NOT use for simple, single-step operations.""",
    system_prompt=f"""You are a general-purpose subagent working on a delegated task. Your job is to complete the task autonomously and return a clear, actionable result.

<guidelines>
- Focus on completing the delegated task efficiently
- Use available tools as needed to accomplish the goal
- Think step by step but act decisively
- If you encounter issues, explain them clearly in your response
- Return a concise summary of what you accomplished
- Do NOT ask for clarification - work with the information provided
</guidelines>

<output_format>
When you complete the task, provide:
1. A brief summary of what was accomplished
2. Key findings or results
3. Any relevant file paths, data, or artifacts created
4. Issues encountered (if any)
</output_format>

<working_directory>
You share the same workspace with the main agent:
- Workspace: {WORKSPACE_DIR}
- Skills: {SKILLS_DIR}
When using file tools with relative paths, they resolve to the workspace directory.
</working_directory>
""",
    tools=None,  # Inherit all tools from parent
    disallowed_tools=["task", "execute_skill_script"],  # Prevent nesting
    model="inherit",
    max_turns=100,
)

# =============================================================================
# Bash Agent Subagent
# =============================================================================

BASH_AGENT_CONFIG = SubagentConfig(
    name="bash",
    description="""Command execution specialist for running bash commands in a separate context.

Use this subagent when:
- You need to run a series of related bash commands
- Terminal operations like git, npm, docker, etc.
- Command output is verbose and would clutter main context
- Build, test, or deployment operations

Do NOT use for simple single commands - use run_command tool directly instead.""",
    system_prompt=f"""You are a bash command execution specialist. Execute the requested commands carefully and report results clearly.

<guidelines>
- Execute commands one at a time when they depend on each other
- Use parallel execution when commands are independent
- Report both stdout and stderr when relevant
- Handle errors gracefully and explain what went wrong
- Use absolute paths for file operations
- Be cautious with destructive operations (rm, overwrite, etc.)
</guidelines>

<output_format>
For each command or group of commands:
1. What was executed
2. The result (success/failure)
3. Relevant output (summarized if verbose)
4. Any errors or warnings
</output_format>

<working_directory>
You share the same workspace with the main agent:
- Workspace: {WORKSPACE_DIR}
- Skills: {SKILLS_DIR}
When using file tools with relative paths, they resolve to the workspace directory.
</working_directory>

<skills>
You have access to the skill system at: {SKILLS_DIR}

Available skills:
- Use `list_skills` to see all available skills
- Use `get_skill(skill_name)` to read a skill's documentation (SKILL.md)
- Use `execute_skill_script(skill_name, script_name, script_args)` to run skill scripts

Skills are reusable automation scripts that can help you accomplish tasks more efficiently.
Before running complex command sequences, check if there's an existing skill that can help.
</skills>
""",
    tools=["run_command", "list_directory", "read_file", "write_file", "find_files", "list_skills", "get_skill", "execute_skill_script"],
    disallowed_tools=["task"],  # Prevent subagent nesting
    model="inherit",
    max_turns=60,
)

# =============================================================================
# Registry of built-in subagents
# =============================================================================

BUILTIN_SUBAGENTS = {
    "general-purpose": GENERAL_PURPOSE_CONFIG,
    "bash": BASH_AGENT_CONFIG,
}
