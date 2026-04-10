"""
Agent state definition for LangGraph.
"""
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(dict):
    """
    State object passed through the LangGraph workflow.

    Attributes:
        messages: List of conversation messages with add_messages reducer
        skill_context: Optional skill context string
        current_task: Current task description
        turn_count: Number of conversation turns
        tool_call_confirmed: Whether user has confirmed pending tool calls
        pending_tool_calls: List of tool calls waiting for confirmation
        enabled_knowledge_bases: List of enabled knowledge base IDs for RAG
        rag_context: Retrieved context from knowledge bases
    """
    messages: Annotated[List[AnyMessage], add_messages]
    skill_context: Optional[str] = None
    current_task: Optional[str] = None
    turn_count: int = 0
    tool_call_confirmed: bool = False
    pending_tool_calls: Optional[List[Dict[str, Any]]] = None
    enabled_knowledge_bases: List[str] = []
    rag_context: str = ""
