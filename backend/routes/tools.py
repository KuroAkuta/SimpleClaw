"""
Tool confirmation endpoints for the Simple Agent Web API.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import ToolConfirmRequest, ToolConfirmResponse
from services.session_manager import session_manager

tools_router = APIRouter(prefix="/api")


@tools_router.post("/tool_confirm", response_model=ToolConfirmResponse)
async def tool_confirm(request: ToolConfirmRequest):
    """Confirm or reject pending tool calls."""
    session_id = request.session_id
    action = request.action  # "confirm" or "reject"

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if action == "confirm":
        session["state"]["tool_call_confirmed"] = True
        return ToolConfirmResponse(
            success=True,
            status="confirmed",
            message="Tool calls confirmed"
        )
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

        return ToolConfirmResponse(
            success=True,
            status="rejected",
            message="Tool calls rejected"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid action, must be 'confirm' or 'reject'")
