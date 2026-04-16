"""
Chat endpoints for the Simple Agent Web API.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sse_starlette.sse import EventSourceResponse

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings  # noqa: F401 - for future use
from graph.builder import build_graph
from models.schemas import ChatRequest, ChatResponse
from services.session_manager import session_manager

chat_router = APIRouter(prefix="/api")


def _build_message_content(message: str, images: Optional[List[str]] = None) -> Any:
    """
    Build message content with optional images.

    Args:
        message: Text message
        images: Optional list of base64 encoded images

    Returns:
        Content suitable for HumanMessage
    """
    if not images:
        return message

    content = [{"type": "text", "text": message}]
    for img_base64 in images:
        # Remove data:image prefix if present
        if img_base64.startswith("data:image"):
            img_base64 = img_base64.split(",")[1]
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
        })
    return content


def _extract_ai_response(messages: List) -> str:
    """
    Extract AI response from message list.

    Args:
        messages: List of messages

    Returns:
        AI response text
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", []):
            return msg.content or ""
    return ""


@chat_router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint."""
    session_id, session = session_manager.get_or_create_session(request.session_id)

    # Create state for graph
    state = {
        "messages": list(session["state"]["messages"]),
        "skill_context": session["state"].get("skill_context"),
        "current_task": request.message,
        "turn_count": session["state"].get("turn_count", 0),
        "tool_call_confirmed": False,
        "enabled_knowledge_bases": request.enabled_knowledge_bases or [],
    }

    # Add user message
    state["messages"].append(HumanMessage(content=_build_message_content(request.message, request.images)))

    # Run agent
    graph = build_graph()
    result = graph.invoke(state)

    # Update session state
    session_manager.update_session_state(
        session_id=session_id,
        messages=result["messages"],
        turn_count=result.get("turn_count", 0),
    )

    # Extract AI response
    ai_response = _extract_ai_response(result["messages"])

    return ChatResponse(session_id=session_id, message=ai_response)


@chat_router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint with SSE."""
    session_id, session = session_manager.get_or_create_session(request.session_id)

    # Create state for graph - load tool_call_confirmed from session to preserve state across iterations
    state = {
        "messages": list(session["state"]["messages"]),
        "skill_context": session["state"].get("skill_context"),
        "current_task": request.message,
        "turn_count": session["state"].get("turn_count", 0),
        "tool_call_confirmed": session["state"].get("tool_call_confirmed", False),
        "pending_tool_calls": session["state"].get("pending_tool_calls"),
        "enabled_knowledge_bases": request.enabled_knowledge_bases or [],
    }

    # Add user message
    state["messages"].append(HumanMessage(content=_build_message_content(request.message, request.images)))

    async def generate():
        graph = build_graph()
        final_messages = list(state["messages"])
        accumulated_ai_content = ""
        subagent_tasks_started = {}  # Track started subagent tasks: {tool_call_id: task_id}

        async for mode, event in graph.astream(state, stream_mode=["messages", "values"]):
            if mode == "messages":
                msg_chunk, metadata = event
                if metadata.get("langgraph_node") == "agent" and isinstance(msg_chunk, AIMessageChunk):
                    if msg_chunk.content and isinstance(msg_chunk.content, str):
                        accumulated_ai_content += msg_chunk.content
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "ai",
                                "content": accumulated_ai_content,
                                "done": False
                            })
                        }
                        await anyio.sleep(0)

            elif mode == "values":
                event_msgs = event.get("messages", [])
                if event_msgs:
                    final_messages = event_msgs
                last_msg = event["messages"][-1] if event.get("messages") else None

                if last_msg:
                    if isinstance(last_msg, AIMessage):
                        has_tool_calls = getattr(last_msg, "tool_calls", [])
                        if has_tool_calls:
                            # Check if these are auto-exec tools (safe/read-only operations)
                            auto_exec_tools = {
                                # Todo management
                                "write_todos", "get_todos", "clear_todos",
                                # Read-only file operations
                                "read_file", "list_directory", "find_files",
                                # Skill system (read-only)
                                "list_skills", "get_skill",
                                # Memory management
                                "load_memory", "save_memory", "clear_memory",
                            }
                            tool_names = [tc.get("name", "") for tc in has_tool_calls]
                            all_auto_exec = all(name in auto_exec_tools for name in tool_names)

                            # Debug logging
                            print(f"[DEBUG] Tool calls: {tool_names}, all_auto_exec: {all_auto_exec}, confirmed: {event.get('tool_call_confirmed', False)}")

                            # Only require confirmation for non-auto-exec tools AND not already confirmed
                            if not all_auto_exec and not event.get("tool_call_confirmed", False):
                                # Non-auto-exec tools, wait for user confirmation
                                print(f"[DEBUG] Waiting for confirmation")
                                yield {
                                    "event": "tool_pending",
                                    "data": json.dumps({
                                        "type": "tool_pending",
                                        "tool_calls": has_tool_calls,
                                        "content": accumulated_ai_content,
                                        "waiting_confirmation": True
                                    })
                                }
                                session_manager.update_session_state(
                                    session_id=session_id,
                                    messages=final_messages,
                                    turn_count=event.get("turn_count", 0),
                                    tool_call_confirmed=False,
                                    pending_tool_calls=has_tool_calls
                                )
                                await anyio.sleep(0)
                                return
                            elif all_auto_exec:
                                # Auto-exec tools - let graph continue without asking for confirmation
                                print(f"[DEBUG] Auto-exec, continuing")
                                state["tool_call_confirmed"] = True  # Update graph state for tool_node
                                session_manager.update_session_state(
                                    session_id=session_id,
                                    messages=final_messages,
                                    turn_count=event.get("turn_count", 0),
                                    tool_call_confirmed=True,
                                    pending_tool_calls=has_tool_calls
                                )
                    elif isinstance(last_msg, ToolMessage):
                        # Tool execution result - send it to frontend
                        accumulated_ai_content = ""
                        tool_name = getattr(last_msg, "name", "")

                        # Debug logging for tool execution
                        print(f"[DEBUG] ToolMessage received: name={tool_name}, content={str(last_msg.content)[:50]}...")

                        # Check for subagent task completion
                        if tool_name == "task" or tool_name == "task_async":
                            task_id = subagent_tasks_started.get(last_msg.tool_call_id, "sync-task")
                            tool_result = str(last_msg.content) if last_msg.content else ""

                            # Check for error/failure
                            if tool_result.startswith("Task failed:") or tool_result.startswith("Error:"):
                                yield {
                                    "event": "subagent_failed",
                                    "data": json.dumps({
                                        "type": "subagent_failed",
                                        "task_id": task_id,
                                        "error": tool_result
                                    })
                                }
                            else:
                                yield {
                                    "event": "subagent_completed",
                                    "data": json.dumps({
                                        "type": "subagent_completed",
                                        "task_id": task_id,
                                        "result": tool_result
                                    })
                                }
                            await anyio.sleep(0)

                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "tool",
                                "content": last_msg.content,
                                "tool_name": last_msg.name
                            })
                        }
                        await anyio.sleep(0)

        # Update session state and reset tool_call_confirmed for next iteration in chat_stream
        session_manager.update_session_state(
            session_id=session_id,
            messages=final_messages,
            turn_count=state.get("turn_count", 0),
            tool_call_confirmed=False,  # Reset for next request
        )

        # Send done signal
        yield {
            "event": "done",
            "data": json.dumps({"session_id": session_id, "done": True})
        }
        await anyio.sleep(0)

    return EventSourceResponse(generate())


@chat_router.post("/chat/resume")
async def chat_resume(request: ChatRequest):
    """Resume a paused session after tool confirmation."""
    session_id = request.session_id

    if not session_id or session_id not in session_manager._sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.get_session(session_id)
    state = session["state"]

    # Check if confirmed
    if not state.get("tool_call_confirmed", False):
        return {
            "status": "pending",
            "session_id": session_id,
            "message": "Waiting for tool confirmation"
        }

    # Execute pending tool calls
    from tools.basic_tools import (
        run_command, read_file, write_file, list_directory, find_files,
        list_skills, get_skill, execute_skill_script,
    )
    from tools.memory_tools import save_memory, load_memory, clear_memory
    from tools.todo_tools import write_todos, get_todos, clear_todos

    # Build base tools dictionary
    tools_by_name = {
        "run_command": run_command,
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
        "find_files": find_files,
        "list_skills": list_skills,
        "get_skill": get_skill,
        "execute_skill_script": execute_skill_script,
        "save_memory": save_memory,
        "load_memory": load_memory,
        "clear_memory": clear_memory,
        "write_todos": write_todos,
        "get_todos": get_todos,
        "clear_todos": clear_todos,
    }

    # Add subagent tools if available
    try:
        from subagent import get_all_subagent_tools
        for tool in get_all_subagent_tools():
            tools_by_name[tool.name] = tool
    except ImportError:
        pass

    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    tool_results = []

    if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tool_call in last_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})

            if tool_name not in tools_by_name:
                result = f"Error: Unknown tool '{tool_name}'"
            else:
                try:
                    tool_func = tools_by_name[tool_name]
                    # For task_async, inject the tool_call_id as task_id for consistent tracking
                    if tool_name == "task_async":
                        tool_args = dict(tool_args)  # Copy to avoid modifying original
                        tool_args["task_id"] = tool_call["id"]
                    result = tool_func.invoke(tool_args)
                except Exception as e:
                    result = f"Error: {e}"

            tool_results.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )

    # Add tool results to state
    state["messages"].extend(tool_results)
    # Reset tool_call_confirmed after executing confirmed tools
    # This ensures subsequent dangerous tools will require confirmation
    state["tool_call_confirmed"] = False

    async def generate():
        # Send tool results first
        for tool_result in tool_results:
            # Check if this is a task_async result - send subagent_started event
            if tool_result.name == "task_async":
                # Extract task_id from the result content
                # Format: "Task started. Task ID: {task_id}. Use get_task_result..."
                result_str = str(tool_result.content)
                if "Task ID:" in result_str:
                    task_id = result_str.split("Task ID:")[1].split(".")[0].strip()
                    yield {
                        "event": "subagent_started",
                        "data": json.dumps({
                            "type": "subagent_started",
                            "task_id": task_id,
                            "subagent_type": "general-purpose",
                            "description": "子 agent 任务"
                        })
                    }
                    await anyio.sleep(0)

            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "tool",
                    "content": str(tool_result.content),
                    "tool_name": tool_result.name
                })
            }
            await anyio.sleep(0)

        graph = build_graph()
        final_messages = list(state["messages"])
        accumulated_ai_content = ""

        async for mode, event in graph.astream(state, stream_mode=["messages", "values"]):
            if mode == "messages":
                msg_chunk, metadata = event
                if metadata.get("langgraph_node") == "agent" and isinstance(msg_chunk, AIMessageChunk):
                    if msg_chunk.content and isinstance(msg_chunk.content, str):
                        accumulated_ai_content += msg_chunk.content
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "ai",
                                "content": accumulated_ai_content,
                                "done": False
                            })
                        }
                        await anyio.sleep(0)

            elif mode == "values":
                event_msgs = event.get("messages", [])
                if event_msgs:
                    final_messages = event_msgs
                last_msg = event["messages"][-1] if event.get("messages") else None

                if last_msg:
                    if isinstance(last_msg, AIMessage):
                        has_tool_calls = getattr(last_msg, "tool_calls", [])
                        if has_tool_calls:
                            # Check if these are auto-exec tools (same logic as chat_stream)
                            auto_exec_tools = {
                                # Todo management
                                "write_todos", "get_todos", "clear_todos",
                                # Read-only file operations
                                "read_file", "list_directory", "find_files",
                                # Skill system (read-only)
                                "list_skills", "get_skill",
                                # Memory management
                                "load_memory", "save_memory", "clear_memory",
                            }
                            tool_names = [tc.get("name", "") for tc in has_tool_calls]
                            all_auto_exec = all(name in auto_exec_tools for name in tool_names)

                            # Debug logging
                            print(f"[DEBUG] [chat_resume] Tool calls: {tool_names}, all_auto_exec: {all_auto_exec}")

                            # Only require confirmation for non-auto-exec tools
                            if not all_auto_exec:
                                yield {
                                    "event": "tool_pending",
                                    "data": json.dumps({
                                        "type": "tool_pending",
                                        "tool_calls": has_tool_calls,
                                        "content": accumulated_ai_content,
                                        "waiting_confirmation": True
                                    })
                                }
                                session_manager.update_session_state(
                                    session_id=session_id,
                                    messages=final_messages,
                                    turn_count=event.get("turn_count", 0),
                                    tool_call_confirmed=False,
                                    pending_tool_calls=has_tool_calls
                                )
                                await anyio.sleep(0)
                                return
                            # else: auto-exec tools, let graph continue
                            elif all_auto_exec:
                                # Auto-exec tools - let graph continue without asking for confirmation
                                print(f"[DEBUG] [chat_resume] Auto-exec, continuing")
                                state["tool_call_confirmed"] = True  # Update graph state for tool_node
                                session_manager.update_session_state(
                                    session_id=session_id,
                                    messages=final_messages,
                                    turn_count=event.get("turn_count", 0),
                                    tool_call_confirmed=True,
                                    pending_tool_calls=has_tool_calls
                                )
                    elif isinstance(last_msg, ToolMessage):
                        accumulated_ai_content = ""
                        tool_name = getattr(last_msg, "name", "")

                        # Debug logging for tool execution
                        print(f"[DEBUG] [chat_resume] ToolMessage received: name={tool_name}, content={str(last_msg.content)[:50]}...")

                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "tool",
                                "content": last_msg.content,
                                "tool_name": last_msg.name
                            })
                        }
                        await anyio.sleep(0)

        # Update session state and reset tool_call_confirmed for next iteration in chat_resume
        session_manager.update_session_state(
            session_id=session_id,
            messages=final_messages,
            turn_count=state.get("turn_count", 0),
            tool_call_confirmed=False,  # Reset for next request
        )

        # Send done signal
        yield {
            "event": "done",
            "data": json.dumps({"session_id": session_id, "done": True})
        }
        await anyio.sleep(0)

    return EventSourceResponse(generate())