"""
Session management endpoints for the Simple Agent Web API.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    SessionsResponse,
    CreateSessionResponse,
    DeleteSessionResponse,
)
from services.session_manager import session_manager

sessions_router = APIRouter(prefix="/api")


@sessions_router.get("/sessions", response_model=SessionsResponse)
async def list_sessions():
    """List all sessions."""
    sessions = session_manager.list_sessions()
    return SessionsResponse(sessions=sessions)


@sessions_router.post("/sessions", response_model=CreateSessionResponse)
async def create_session():
    """Create a new session."""
    session_id = session_manager.create_session()
    return CreateSessionResponse(session_id=session_id)


@sessions_router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str):
    """Delete a session."""
    success = session_manager.delete_session(session_id)
    return DeleteSessionResponse(success=success)


@sessions_router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """Get conversation history for a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = []
    for msg in session["state"].get("messages", []):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
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
            if msg.content:
                messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            messages.append({"role": "tool", "content": msg.content, "name": msg.name})

    return {"messages": messages}


@sessions_router.get("/sessions/{session_id}/debug")
async def debug_session(session_id: str):
    """Debug endpoint to see raw session state."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session["state"]
    debug_info = {
        "session_id": session_id,
        "turn_count": state.get("turn_count", 0),
        "message_count": len(state.get("messages", [])),
        "messages": []
    }

    for i, msg in enumerate(state.get("messages", [])):
        msg_info = {
            "index": i,
            "type": type(msg).__name__,
            "has_content": bool(getattr(msg, "content", None)),
            "content_preview": str(getattr(msg, "content", ""))[:50] if msg.content else None,
            "has_tool_calls": bool(getattr(msg, "tool_calls", []))
        }
        debug_info["messages"].append(msg_info)

    return debug_info


@sessions_router.get("/sessions/{session_id}/pending_tools")
async def get_pending_tools(session_id: str):
    """Get pending tool calls waiting for confirmation."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
