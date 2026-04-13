"""
Session manager for handling user conversations.
"""
import uuid
from typing import Any, Dict, List, Optional


class SessionManager:
    """
    In-memory session storage for managing user conversations.

    Each session contains:
    - created: Session creation timestamp/ID
    - name: Session name (default: "新会话")
    - state: AgentState dictionary with messages and metadata
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, name: str = "新会话") -> str:
        """
        Create a new session.

        Args:
            name: Optional session name, defaults to "新会话"

        Returns:
            New session ID
        """
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "created": str(uuid.uuid4()),
            "name": name,
            "state": self._create_empty_state()
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session data or None if not found
        """
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Dict[str, str]]:
        """
        List all sessions.

        Returns:
            List of session info dictionaries with id, created, and name fields
        """
        return [
            {"id": sid, "created": s.get("created"), "name": s.get("name", "新会话")}
            for sid, s in self._sessions.items()
        ]

    def update_session_name(self, session_id: str, name: str) -> None:
        """
        Update session name.

        Args:
            session_id: Session identifier
            name: New session name
        """
        if session_id in self._sessions:
            self._sessions[session_id]["name"] = name

    def update_session_state(
        self,
        session_id: str,
        messages: List[Any],
        turn_count: int,
        tool_call_confirmed: bool = False,
        pending_tool_calls: Optional[List[Dict]] = None
    ) -> None:
        """
        Update session state with new messages and metadata.

        Args:
            session_id: Session identifier
            messages: Updated message list
            turn_count: Current turn count
            tool_call_confirmed: Whether tool calls are confirmed
            pending_tool_calls: Pending tool calls if any
        """
        if session_id not in self._sessions:
            return

        self._sessions[session_id]["state"]["messages"] = messages
        self._sessions[session_id]["state"]["turn_count"] = turn_count
        self._sessions[session_id]["state"]["tool_call_confirmed"] = tool_call_confirmed
        self._sessions[session_id]["state"]["pending_tool_calls"] = pending_tool_calls

    def get_or_create_session(self, session_id: Optional[str] = None) -> tuple[str, Dict[str, Any]]:
        """
        Get existing session or create new one.

        Args:
            session_id: Optional session ID, creates new if None or not found

        Returns:
            Tuple of (session_id, session_data)
        """
        if not session_id or session_id not in self._sessions:
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {
                "created": str(uuid.uuid4()),
                "name": "新会话",
                "state": self._create_empty_state()
            }
        return session_id, self._sessions[session_id]

    @staticmethod
    def _create_empty_state() -> Dict[str, Any]:
        """Create an empty agent state."""
        return {
            "messages": [],
            "skill_context": None,
            "current_task": None,
            "turn_count": 0,
            "tool_call_confirmed": False,
            "pending_tool_calls": None,
        }


# Global session manager instance
session_manager = SessionManager()
