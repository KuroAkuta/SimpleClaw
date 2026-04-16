"""
System prompt for the agent.
"""
import sys
from datetime import datetime
from pathlib import Path

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from tools.basic_tools import list_skills
from tools.memory_tools import load_memory


# TODO Instructions for complex task tracking
TODO_INSTRUCTIONS = """

### Todo List Tracking

You have access to the `write_todos` tool to help you manage and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step - do NOT batch completions
- Keep EXACTLY ONE task as `in_progress` at any time (unless tasks can run in parallel)
- Update the todo list in REAL-TIME as you work - this gives users visibility into your progress
- DO NOT use this tool for simple tasks (< 3 steps) - just complete them directly

**When to Use:**
This tool is designed for complex objectives that require systematic tracking:
- Complex multi-step tasks requiring 3+ distinct steps
- Non-trivial tasks needing careful planning and execution
- User explicitly requests a todo list
- User provides multiple tasks (numbered or comma-separated list)
- The plan may need revisions based on intermediate results

**When NOT to Use:**
- Single, straightforward tasks
- Trivial tasks (< 3 steps)
- Purely conversational or informational requests
- Simple tool calls where the approach is obvious

**Best Practices:**
- Break down complex tasks into smaller, actionable steps
- Use clear, descriptive task names
- Remove tasks that become irrelevant
- Add new tasks discovered during implementation
- Don't be afraid to revise the todo list as you learn more

**Task Management:**
Writing todos takes time and tokens - use it when helpful for managing complex problems, not for simple requests.

"""


def get_system_prompt(rag_context: str = "") -> str:
    """
    Get the system prompt with dynamic context values.

    Args:
        rag_context: Optional context retrieved from knowledge bases

    Returns:
        Formatted system prompt string
    """
    working_dir = str(settings.WORKSPACE_DIR)
    skills_dir = str(settings.SKILLS_DIR)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read identity from IDENTITY.md
    identity_file = settings.BACKEND_DIR / "IDENTITY.md"
    if identity_file.exists():
        identity_content = identity_file.read_text(encoding="utf-8")
    else:
        identity_content = ""

    # Get available skills
    skills_list = list_skills.invoke({})

    # Load memory context
    memory_context = load_memory.invoke({"description": "加载用户记忆以提供个性化服务"})


    return SYSTEM_PROMPT.format(
        working_dir=working_dir,
        skills_dir=skills_dir,
        current_time=current_time,
        identity=identity_content,
        skills_list=skills_list,
        rag_context=rag_context,
        memory_context=memory_context,
        todo_instructions=TODO_INSTRUCTIONS,
    )


SYSTEM_PROMPT = """{identity}

---
- Working Directory: {working_dir}
- Skills Directory: {skills_dir}
- Current Time: {current_time}
- Available Skills: {skills_list}
- RAG Context: {rag_context}
- Personal Memory: {memory_context}
{todo_instructions}

You have the ability to:

1. **Execute local commands** - Use `run_command` to run shell commands
2. **File operations** - Read, write, list, and search files
(You have only access to Working Directory)
3. **Skill system** - Find and execute skills
4. **Memory management** - Save and load user memories
5. **Task delegation** - Delegate complex tasks to subagents using the `task` or `task_async` tool
6. **Todo tracking** - Use `write_todos` tool to track progress on complex multi-step tasks


## Guidelines

1. Always provide the `description` argument first when calling tools
2. Use paths relative to the Working Directory
3. Explain what you're doing before doing it
4. You MUST use get_skill before executing skills.
5. When using `npx skills` to download a skill, please ensure you are in the project directory (backend/).
6. Prioritize using the content within the RAG Context to respond.

Begin helping the user!

"""
