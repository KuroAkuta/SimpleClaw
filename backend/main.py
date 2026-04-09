"""
Simple Agent Web - Backend
FastAPI server with SSE streaming support
"""

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator, Annotated
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import json

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

# Add parent directory to path for tools import
sys.path.insert(0, str(Path(__file__).parent))
from tools import get_all_tools, get_skills_dir


# =============================================================================
# Configuration
# =============================================================================

class Config:
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    CUSTOM_MODEL_NAME = os.getenv("CUSTOM_MODEL_NAME", "")
    CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL", "")
    CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
    MAX_TURNS = int(os.getenv("MAX_TURNS", "50"))


# =============================================================================
# State Definition
# =============================================================================

class AgentState(dict):
    messages: Annotated[List, add_messages]
    skill_context: Optional[str] = None
    current_task: Optional[str] = None
    turn_count: int = 0
    tool_call_confirmed: bool = False  # True = user confirmed, False = waiting or not confirmed
    pending_tool_calls: Optional[List[Dict]] = None  # Store pending tool calls for confirmation


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are Simple Agent, a helpful AI assistant with the ability to:

1. **Execute local commands** - Use `run_command` to run shell commands
2. **File operations** - Read, write, list, and search files
3. **Skill system** - Find and execute skills

## Available Tools

### Command Execution (Under Windows)
- `run_command(description, command)` - Execute a shell command

### File Operations
- `read_file(description, path)` - Read file contents
- `write_file(description, path, content)` - Write to a file
- `list_directory(description, path)` - List directory contents
- `find_files(description, pattern, path)` - Find files by glob pattern

### Skill System
- `list_skills()` - List all installed skills
- `get_skill(skill_name)` - Get full skill content
- `execute_skill_script(skill_name, script_name, args)` - Run skill scripts
- When using `npx skills` to download skill, please ensure you are in the project directory. Additionally, the command must comply with Windows requirements.

## Guidelines

1. Always provide the `description` argument first when calling tools
2. Use absolute paths or paths relative to the project directory
3. Explain what you're doing before doing it

## Context

- Working Directory: {working_dir}
- Skills Directory: {skills_dir}
- Current Time: {current_time}

Begin helping the user!
"""


# =============================================================================
# Model Creation
# =============================================================================

_model_cache = None
_model_with_tools_cache = None


def create_model():
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    if Config.CUSTOM_MODEL_NAME and Config.CUSTOM_BASE_URL:
        _model_cache = ChatOpenAI(
            model=Config.CUSTOM_MODEL_NAME,
            api_key=Config.CUSTOM_API_KEY or Config.OPENAI_API_KEY,
            base_url=Config.CUSTOM_BASE_URL,
            temperature=0.7,
        )
        return _model_cache

    if not Config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    _model_cache = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        api_key=Config.OPENAI_API_KEY,
        temperature=0.7,
    )
    return _model_cache


def get_model_with_tools():
    global _model_with_tools_cache
    if _model_with_tools_cache is not None:
        return _model_with_tools_cache

    model = create_model()
    tools = get_all_tools()
    _model_with_tools_cache = model.bind_tools(tools)
    return _model_with_tools_cache


# =============================================================================
# Graph Nodes
# =============================================================================

_pending_tool_calls = None


async def agent_node(state: AgentState):
    global _pending_tool_calls

    model_with_tools = get_model_with_tools()
    working_dir = str(Path(__file__).parent)
    skills_dir = str(get_skills_dir())
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    system_message = SystemMessage(
        content=SYSTEM_PROMPT.format(working_dir=working_dir, skills_dir=skills_dir, current_time=current_time)
    )
    messages = [system_message] + state["messages"]

    response = await model_with_tools.ainvoke(messages)

    has_tool_calls = hasattr(response, 'tool_calls') and response.tool_calls
    already_confirmed = state.get("tool_call_confirmed", False)

    if has_tool_calls and not already_confirmed:
        # Store pending tool calls and wait for user confirmation
        pending_calls = response.tool_calls
        return {
            "messages": [response],
            "turn_count": state.get("turn_count", 0) + 1,
            "tool_call_confirmed": False,  # Still waiting for confirmation
            "pending_tool_calls": pending_calls,  # Store for confirmation endpoint
        }
    elif has_tool_calls and already_confirmed:
        # Already confirmed, proceed normally
        pass
    else:
        pass

    new_turn_count = state.get("turn_count", 0) + 1
    return {
        "messages": [response],
        "turn_count": new_turn_count,
        "tool_call_confirmed": False,
        "pending_tool_calls": None,  # Clear after processing
    }


async def tool_node(state: AgentState):
    from tools import (
        run_command, read_file, write_file, list_directory, find_files,
        list_skills, get_skill, execute_skill_script,
    )

    tools_by_name = {
        "run_command": run_command,
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
        "find_files": find_files,
        "list_skills": list_skills,
        "get_skill": get_skill,
        "execute_skill_script": execute_skill_script,
    }

    last_message = state["messages"][-1]

    # Check if tool calls are confirmed
    if not state.get("tool_call_confirmed", False):
        # Not confirmed yet, don't execute tools
        return {"messages": [], "tool_call_confirmed": False}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": [], "tool_call_confirmed": False}

    results = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})

        if tool_name not in tools_by_name:
            result = f"Error: Unknown tool '{tool_name}'"
        else:
            try:
                tool_func = tools_by_name[tool_name]
                result = tool_func.invoke(tool_args)
            except Exception as e:
                result = f"Error: {e}"

        results.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return {"messages": results, "tool_call_confirmed": False}


def should_continue(state: AgentState):
    if state.get("turn_count", 0) >= Config.MAX_TURNS:
        return "end"

    last_message = state["messages"][-1]
    has_tool_calls = hasattr(last_message, "tool_calls") and last_message.tool_calls

    # If has tool calls but not confirmed yet, go to tools node (which will check confirmation)
    if has_tool_calls:
        return "tools"

    if isinstance(last_message, ToolMessage):
        return "agent"

    return "end"


# =============================================================================
# Graph Building (per-session)
# =============================================================================

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "agent": "agent", "end": END},
    )
    graph.add_edge("tools", "agent")
    return graph.compile()


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(title="Simple Agent Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-memory session storage
sessions: Dict[str, Dict[str, Any]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    images: Optional[List[str]] = None  # List of base64 encoded images
    images: Optional[List[str]] = None  # List of base64 encoded images


class ChatResponse(BaseModel):
    session_id: str
    message: str


class ToolConfirmRequest(BaseModel):
    session_id: str
    action: str  # "confirm" or "reject"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": [{"id": sid, "created": s.get("created")} for sid, s in sessions.items()]}


@app.post("/api/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "created": str(uuid.uuid4()),
        "state": {
            "messages": [],
            "skill_context": None,
            "current_task": None,
            "turn_count": 0,
            "tool_call_confirmed": False,
        }
    }
    return {"session_id": session_id}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"success": True}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint"""
    session_id = request.session_id

    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            "state": {
                "messages": [],
                "skill_context": None,
                "current_task": None,
                "turn_count": 0,
                "tool_call_confirmed": False,
            }
        }

    session = sessions[session_id]

    # Create a copy of state for the graph to work with
    state = {
        "messages": list(session["state"]["messages"]),
        "skill_context": session["state"].get("skill_context"),
        "current_task": request.message,
        "turn_count": session["state"].get("turn_count", 0),
        "tool_call_confirmed": False,
    }

    # Add user message with images if present
    if request.images and len(request.images) > 0:
        # Build message content with text and images
        content = [{"type": "text", "text": request.message}]
        for img_base64 in request.images:
            # Remove data:image prefix if present
            if img_base64.startswith("data:image"):
                img_base64 = img_base64.split(",")[1]
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
            })
        state["messages"].append(HumanMessage(content=content))
    else:
        state["messages"].append(HumanMessage(content=request.message))

    # Run agent
    graph = build_graph()
    result = graph.invoke(state)

    # Update session state with all messages
    session["state"]["messages"] = result["messages"]
    session["state"]["turn_count"] = result.get("turn_count", 0)

    # Get AI response
    ai_response = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", []):
            ai_response = msg.content
            break

    return {"session_id": session_id, "message": ai_response}


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint with SSE"""
    session_id = request.session_id

    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            "state": {
                "messages": [],
                "skill_context": None,
                "current_task": None,
                "turn_count": 0,
                "tool_call_confirmed": False,
                "pending_tool_calls": None,
            }
        }

    session = sessions[session_id]

    # Create a copy of state for the graph to work with
    state = {
        "messages": list(session["state"]["messages"]),
        "skill_context": session["state"].get("skill_context"),
        "current_task": request.message,
        "turn_count": session["state"].get("turn_count", 0),
        "tool_call_confirmed": False,
        "pending_tool_calls": None,
    }

    # Add user message with images if present
    if request.images and len(request.images) > 0:
        # Build message content with text and images
        content = [{"type": "text", "text": request.message}]
        for img_base64 in request.images:
            # Remove data:image prefix if present
            if img_base64.startswith("data:image"):
                img_base64 = img_base64.split(",")[1]
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
            })
        state["messages"].append(HumanMessage(content=content))
    else:
        state["messages"].append(HumanMessage(content=request.message))

    async def generate():
            import anyio

            graph = build_graph()
            final_messages = list(state["messages"])
            accumulated_ai_content = ""  # 用于累加文字内容

            # 同时监听 messages(用于流式输出文字) 和 values(用于更新状态和拦截工具)
            async for mode, event in graph.astream(state, stream_mode=["messages", "values"]):
                
                if mode == "messages":
                    msg_chunk, metadata = event
                    # 只提取 agent 节点产生的文字 Token
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
                            await anyio.sleep(0)  # Force flush
                            
                elif mode == "values":
                    event_msgs = event.get("messages", [])
                    if event_msgs:
                        final_messages = event_msgs
                    last_msg = event["messages"][-1] if event.get("messages") else None

                    if last_msg:
                        # 拦截并处理工具调用
                        if isinstance(last_msg, AIMessage):
                            has_tool_calls = getattr(last_msg, "tool_calls", [])
                            if has_tool_calls and not event.get("tool_call_confirmed", False):
                                yield {
                                    "event": "tool_pending",
                                    "data": json.dumps({
                                        "type": "tool_pending",
                                        "tool_calls": has_tool_calls,
                                        "content": accumulated_ai_content,
                                        "waiting_confirmation": True
                                    })
                                }
                                session["state"]["messages"] = final_messages
                                session["state"]["turn_count"] = event.get("turn_count", 0)
                                session["state"]["pending_tool_calls"] = has_tool_calls
                                session["state"]["tool_call_confirmed"] = False
                                await anyio.sleep(0)
                                return
                        elif isinstance(last_msg, ToolMessage):
                            accumulated_ai_content = "" # 遇到工具调用后，清空累加器，为下一轮 AI 回复做准备
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "type": "tool",
                                    "content": last_msg.content,
                                    "tool_name": last_msg.name
                                })
                            }
                            await anyio.sleep(0)

            # Update session state with final messages
            session["state"]["messages"] = final_messages
            session["state"]["turn_count"] = state.get("turn_count", 0)
            session["state"]["tool_call_confirmed"] = False
            session["state"]["pending_tool_calls"] = None

            # Send done signal
            yield {
                "event": "done",
                "data": json.dumps({"session_id": session_id, "done": True})
            }
            await anyio.sleep(0)

    return EventSourceResponse(generate())


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """Get conversation history for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    messages = []
    for msg in session["state"].get("messages", []):
        if isinstance(msg, HumanMessage):
            # Handle multi-modal content (list of dicts)
            content = msg.content
            if isinstance(content, list):
                # Convert to serializable format
                serialized_content = []
                for item in content:
                    if isinstance(item, dict):
                        serialized_content.append(item)
                    else:
                        serialized_content.append({"type": "text", "text": str(item)})
                messages.append({"role": "user", "content": serialized_content})
            else:
                messages.append({"role": "user", "content": content})
        elif isinstance(msg, AIMessage):
            # Include all AI messages that have content (regardless of tool_calls)
            # tool_calls being present doesn't mean the message isn't a response
            if msg.content:
                messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            messages.append({"role": "tool", "content": msg.content, "name": msg.name})

    return {"messages": messages}


@app.get("/api/sessions/{session_id}/debug")
async def debug_session(session_id: str):
    """Debug endpoint to see raw session state"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    debug_info = {
        "session_id": session_id,
        "turn_count": session["state"].get("turn_count", 0),
        "message_count": len(session["state"].get("messages", [])),
        "messages": []
    }

    for i, msg in enumerate(session["state"].get("messages", [])):
        msg_info = {
            "index": i,
            "type": type(msg).__name__,
            "has_content": bool(getattr(msg, "content", None)),
            "content_preview": str(getattr(msg, "content", ""))[:50] if msg.content else None,
            "has_tool_calls": bool(getattr(msg, "tool_calls", []))
        }
        debug_info["messages"].append(msg_info)

    return debug_info


@app.get("/api/sessions/{session_id}/pending_tools")
async def get_pending_tools(session_id: str):
    """Get pending tool calls waiting for confirmation"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    state = session["state"]

    # Check if there are pending tool calls
    pending_calls = state.get("pending_tool_calls")
    if pending_calls:
        return {
            "has_pending": True,
            "tool_calls": pending_calls,
            "confirmed": state.get("tool_call_confirmed", False)
        }

    # Also check last message for tool calls
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return {
                "has_pending": True,
                "tool_calls": last_msg.tool_calls,
                "confirmed": state.get("tool_call_confirmed", False)
            }

    return {"has_pending": False, "tool_calls": [], "confirmed": False}


@app.post("/api/tool_confirm")
async def tool_confirm(request: ToolConfirmRequest):
    """Confirm or reject pending tool calls"""
    session_id = request.session_id
    action = request.action  # "confirm" or "reject"

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if action == "confirm":
        session["state"]["tool_call_confirmed"] = True
        return {"success": True, "status": "confirmed", "message": "Tool calls confirmed"}
    elif action == "reject":
        # Clear pending tool calls and reset state
        session["state"]["tool_call_confirmed"] = False
        session["state"]["pending_tool_calls"] = None
        # Remove tool calls from last AI message to prevent re-execution
        messages = session["state"].get("messages", [])
        if messages:
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], AIMessage) and getattr(messages[i], "tool_calls", []):
                    messages[i].tool_calls = []
                    break
        return {"success": True, "status": "rejected", "message": "Tool calls rejected"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action, must be 'confirm' or 'reject'")


@app.post("/api/chat/resume")
async def chat_resume(request: ChatRequest):
    """Resume a paused session after tool confirmation"""
    session_id = request.session_id

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    state = session["state"]

    print(f"[RESUME] Session state before resume:")
    print(f"[RESUME]   tool_call_confirmed: {state.get('tool_call_confirmed')}")
    print(f"[RESUME]   message count: {len(state.get('messages', []))}")
    if state.get('messages'):
        last_msg = state['messages'][-1]
        print(f"[RESUME]   last message type: {type(last_msg).__name__}")
        print(f"[RESUME]   last message has tool_calls: {bool(getattr(last_msg, 'tool_calls', []))}")

    # Check if confirmed
    if not state.get("tool_call_confirmed", False):
        # Not confirmed yet, return pending status
        return {
            "status": "pending",
            "session_id": session_id,
            "message": "Waiting for tool confirmation"
        }

    # Manually execute tool_node first, then continue with graph
    from tools import (
        run_command, read_file, write_file, list_directory, find_files,
        list_skills, get_skill,
        execute_skill_script,
    )

    tools_by_name = {
        "run_command": run_command,
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
        "find_files": find_files,
        "list_skills": list_skills,
        "get_skill": get_skill,
        "execute_skill_script": execute_skill_script,
    }

    # Find and execute pending tool calls
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None
    tool_results = []

    print(f"[RESUME] Executing {len(last_msg.tool_calls) if last_msg and getattr(last_msg, 'tool_calls', []) else 0} tool calls")

    if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tool_call in last_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})

            print(f"[RESUME] Executing tool: {tool_name}")

            if tool_name not in tools_by_name:
                result = f"Error: Unknown tool '{tool_name}'"
            else:
                try:
                    tool_func = tools_by_name[tool_name]
                    result = tool_func.invoke(tool_args)
                    print(f"[RESUME] Tool result: {str(result)[:100]}...")
                except Exception as e:
                    result = f"Error: {e}"
                    print(f"[RESUME] Tool error: {e}")

            tool_results.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )

    # Add tool results to state
    state["messages"].extend(tool_results)

    print(f"[RESUME] Messages after adding tool results: {len(state['messages'])}")

    # Now resume graph execution from agent node
    graph = build_graph()

    async def generate():
        import anyio

        # Send tool results first
        for tool_result in tool_results:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "tool",
                    "content": str(tool_result.content),
                    "tool_name": tool_result.name
                })
            }
            await anyio.sleep(0)

        final_messages = list(state["messages"])
        accumulated_ai_content = ""

        # 双重监听模式：同时监听 messages 和 values
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
                            # Nested tool calls - need confirmation again
                            yield {
                                "event": "tool_pending",
                                "data": json.dumps({
                                    "type": "tool_pending",
                                    "tool_calls": has_tool_calls,
                                    "content": accumulated_ai_content,
                                    "waiting_confirmation": True
                                })
                            }
                            session["state"]["messages"] = final_messages
                            session["state"]["turn_count"] = event.get("turn_count", 0)
                            session["state"]["pending_tool_calls"] = has_tool_calls
                            session["state"]["tool_call_confirmed"] = False
                            await anyio.sleep(0)
                            return
                    elif isinstance(last_msg, ToolMessage):
                        accumulated_ai_content = ""
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "tool",
                                "content": last_msg.content,
                                "tool_name": last_msg.name
                            })
                        }
                        await anyio.sleep(0)

        # Update session state
        session["state"]["messages"] = final_messages
        session["state"]["turn_count"] = state.get("turn_count", 0)
        session["state"]["tool_call_confirmed"] = False
        session["state"]["pending_tool_calls"] = None

        # Send done signal
        yield {
            "event": "done",
            "data": json.dumps({"session_id": session_id, "done": True})
        }
        await anyio.sleep(0)

    return EventSourceResponse(generate())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
