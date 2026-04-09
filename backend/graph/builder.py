"""
LangGraph builder for creating the agent workflow graph.
"""
import sys
from pathlib import Path

from langgraph.graph import StateGraph, START, END

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.state import AgentState
from graph.nodes import agent_node, tool_node, should_continue


def build_graph():
    """
    Build and compile the LangGraph workflow.

    The graph structure:
    1. Start -> agent node
    2. Agent node -> conditional edges (tools/agent/end)
    3. Tools node -> agent node (loop back for continued conversation)

    Returns:
        Compiled LangGraph ready for invocation
    """
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
