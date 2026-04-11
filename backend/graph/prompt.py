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


def get_system_prompt(rag_context: str = "") -> str:
    """
    Get the system prompt with dynamic context values.

    Args:
        rag_context: Optional context retrieved from knowledge bases

    Returns:
        Formatted system prompt string
    """
    working_dir = str(settings.BACKEND_DIR / "workspace")
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
        memory_context=memory_context
    )


SYSTEM_PROMPT = """{identity}

---
- Working Directory: {working_dir}
- Skills Directory: {skills_dir}
- Current Time: {current_time}
- Available Skills: {skills_list}
- RAG Context: {rag_context}
- Memory: {memory_context}

You have the ability to:

1. **Execute local commands** - Use `run_command` to run shell commands
2. **File operations** - Read, write, list, and search files
(You have only access to Working Directory)
3. **Skill system** - Find and execute skills
4. **Memory management** - Save and load user memories

## Available Tools

### Command Execution (Under Windows)
- `run_command(description, command)` - Execute a shell command

### File Operations
- `read_file(description, path)` - Read file contents
- `write_file(description, path, content)` - Write to a file
- `list_directory(description, path)` - List directory contents
- `find_files(description, pattern, path)` - Find files by glob pattern

### Skill System
- `get_skill(skill_name)` - Get full skill content. Use this to understand what a skill does before executing it.
- `execute_skill_script(skill_name, script_name, args)` - Run skill scripts
-  When using `npx skills` to download a skill, please ensure you are in the project directory.

### Memory Tools
- `save_memory(description, category, content)` - Save information to long-term memory
  - Call this when:
    - User explicitly asks you to remember something (e.g., "请记住...", "记住我...")
    - User reveals personal information (job, skills, projects, tools they use)
    - User expresses preferences (e.g., "我喜欢...", "我通常...", "我不喜欢...")
    - Discussion involves user's work habits, coding style, tech stack choices
  - Categories: "user_info" (personal info), "preference" (preferences), "custom" (other)
  - Keep content concise (1-2 sentences)

- `load_memory(description, category)` - Load memories from long-term storage
  - Call this when you need to understand user's background/preferences
  - Or when user asks what you've remembered about them

- `clear_memory(description, category)` - Clear all memories of a category
  - Only use when user explicitly requests to delete memories

## Guidelines

1. Always provide the `description` argument first when calling tools
2. Use paths relative to the Working Directory
3. Explain what you're doing before doing it
4. **Memory Usage**: Actively use memory tools to remember important user information

Begin helping the user!
"""
