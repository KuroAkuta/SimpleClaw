"""
Memory Tools - 简易长期记忆功能

功能：
1. 将用户信息、偏好、明确需要记住的信息存储到 Memory.md
2. 由 AI 决定是否调用记忆工具
3. 记忆信息简洁明了
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from langchain.tools import tool


def get_memory_file_path() -> Path:
    """获取 Memory.md 文件路径"""
    script_dir = Path(__file__).parent.parent
    memory_file = script_dir / "Memory.md"
    return memory_file


def parse_memory_file(memory_file: Path) -> dict:
    """
    解析 Memory.md 文件内容

    返回结构：
    {
        "user_info": [...],
        "preferences": [...],
        "custom_memories": [...]
    }
    """
    if not memory_file.exists():
        return {"user_info": [], "preferences": [], "custom_memories": []}

    content = memory_file.read_text(encoding="utf-8")

    memories = {
        "user_info": [],
        "preferences": [],
        "custom_memories": []
    }

    current_section = None

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            section = line.replace("## ", "").lower()
            if "user" in section or "用户" in section:
                current_section = "user_info"
            elif "prefer" in section or "偏好" in section:
                current_section = "preferences"
            else:
                current_section = "custom_memories"
        elif line.startswith("- ") and current_section:
            memories[current_section].append(line[2:])

    return memories


@tool
def save_memory(description: str, category: str, content: str) -> str:
    """
    保存信息到长期记忆 (Memory.md)。

    当聊天中出现以下情况时调用此工具：
    1. 用户主动要求你记住某些信息（如"请记住..."、"记住我..."）
    2. 用户透露了个人信息（如职业、技能、项目、使用的工具等）
    3. 用户表达了偏好（如"我喜欢..."、"我通常..."、"我不喜欢..."）
    4. 讨论中涉及用户的工作习惯、编码风格、技术栈选择等

    Args:
        description: 简要说明为什么要保存这条记忆
        category: 记忆类别，必须是以下之一：
            - "user_info": 用户个人信息（职业、技能、项目、背景等）
            - "preference": 用户偏好（工具偏好、编码风格、喜欢/不喜欢等）
            - "custom": 其他需要记住的信息
        content: 要记忆的内容，应该简洁明了（建议 1-2 句话）

    Returns:
        保存结果消息
    """
    try:
        memory_file = get_memory_file_path()

        # 验证类别
        valid_categories = ["user_info", "preference", "custom"]
        if category not in valid_categories:
            return f"错误：无效的记忆类别 '{category}'。请使用：user_info, preference, 或 custom"

        # 确保内容简洁
        content = content.strip()
        if len(content) > 200:
            return f"错误：记忆内容过长（{len(content)}字符），请精简到 200 字符以内"

        if not content:
            return "错误：记忆内容不能为空"

        # 创建文件如果不存在
        if not memory_file.exists():
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            initial_content = """# Memory - 长期记忆

本文件存储用户的长期记忆信息，用于在对话中提供更个性化的服务。

## User Info - 用户信息

## Preferences - 用户偏好

## Custom Memories - 其他记忆

"""
            memory_file.write_text(initial_content, encoding="utf-8")

        # 解析现有记忆，检查是否重复
        existing = parse_memory_file(memory_file)
        section_key = category if category != "custom" else "custom_memories"

        # 检查重复（不区分大小写）
        content_lower = content.lower()
        for existing_memory in existing[section_key]:
            if content_lower in existing_memory.lower() or existing_memory.lower() in content_lower:
                return f"信息已存在于记忆中：{existing_memory}"

        # 追加到新行
        timestamp = datetime.now().strftime("%Y-%m-%d")
        memory_line = f"- [{timestamp}] {content}\n"

        # 读取当前内容
        current_content = memory_file.read_text(encoding="utf-8")

        # 找到对应的 section 并插入
        section_headers = {
            "user_info": "## User Info - 用户信息",
            "preference": "## Preferences - 用户偏好",
            "custom": "## Custom Memories - 其他记忆"
        }

        target_header = section_headers[category]
        lines = current_content.split("\n")

        new_lines = []
        inserted = False

        for i, line in enumerate(lines):
            new_lines.append(line)
            if line.strip() == target_header and not inserted:
                # 在 header 后插入新行
                new_lines.append(memory_line.rstrip())
                inserted = True

        if not inserted:
            # 如果没有找到 header，追加到文件末尾
            new_lines.append("")
            new_lines.append(f"{target_header}")
            new_lines.append(memory_line.rstrip())

        memory_file.write_text("\n".join(new_lines), encoding="utf-8")

        return f"成功保存到记忆：{content}"

    except Exception as e:
        return f"保存记忆失败：{e}"


@tool
def load_memory(description: str, category: Optional[str] = None) -> str:
    """
    从长期记忆 (Memory.md) 中加载已保存的信息。

    当需要了解用户背景、偏好，或用户询问你之前记住了什么时调用此工具。

    Args:
        description: 简要说明为什么要加载记忆
        category: 可选，指定要加载的记忆类别：
            - "user_info": 用户个人信息
            - "preference": 用户偏好
            - "custom": 其他记忆
            - None: 加载所有记忆

    Returns:
        记忆内容字符串
    """
    try:
        memory_file = get_memory_file_path()

        if not memory_file.exists():
            return "暂无记忆记录"

        if category:
            memories = parse_memory_file(memory_file)
            section_key = category if category != "custom" else "custom_memories"
            section_names = {
                "user_info": "用户信息",
                "preference": "用户偏好",
                "custom_memories": "其他记忆"
            }

            items = memories.get(section_key, [])
            if not items:
                return f"{section_names.get(section_key, category)}：暂无记录"

            return f"## {section_names.get(section_key, category)}\n" + "\n".join(f"- {item}" for item in items)
        else:
            # 返回完整文件内容
            return memory_file.read_text(encoding="utf-8")

    except Exception as e:
        return f"加载记忆失败：{e}"


@tool
def clear_memory(description: str, category: str) -> str:
    """
    清空指定类别的所有记忆。

    谨慎使用：仅在用户明确要求删除某类记忆时使用。

    Args:
        description: 简要说明为什么要清空记忆
        category: 要清空的记忆类别：
            - "user_info": 清空用户信息
            - "preference": 清空用户偏好
            - "custom": 清空其他记忆

    Returns:
        清空结果消息
    """
    try:
        memory_file = get_memory_file_path()

        if not memory_file.exists():
            return "记忆文件不存在，无需清空"

        valid_categories = ["user_info", "preference", "custom"]
        if category not in valid_categories:
            return f"错误：无效的记忆类别 '{category}'"

        memories = parse_memory_file(memory_file)
        section_key = category if category != "custom" else "custom_memories"

        if not memories[section_key]:
            return f"{category} 类别本就没有记忆"

        # 清空指定类别
        memories[section_key] = []

        # 重建文件内容
        section_headers = {
            "user_info": "## User Info - 用户信息",
            "preference": "## Preferences - 用户偏好",
            "custom_memories": "## Custom Memories - 其他记忆"
        }

        content = "# Memory - 长期记忆\n\n"
        content += "本文件存储用户的长期记忆信息，用于在对话中提供更个性化的服务。\n\n"

        for key, items in memories.items():
            content += f"{section_headers.get(key, '## ' + key)}\n\n"
            for item in items:
                content += f"- {item}\n"
            content += "\n"

        memory_file.write_text(content, encoding="utf-8")

        return f"已清空 {category} 类别的所有记忆"

    except Exception as e:
        return f"清空记忆失败：{e}"


# =============================================================================
# Tool Collection
# =============================================================================

def get_memory_tools():
    """获取所有记忆工具"""
    return [save_memory, load_memory, clear_memory]
