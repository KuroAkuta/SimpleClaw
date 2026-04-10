"""
LangGraph builder for creating the agent workflow graph.
"""
import sys
from pathlib import Path

from langgraph.graph import StateGraph, START, END

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.state import AgentState
from graph.nodes import agent_node, tool_node, should_continue, rag_retrieval_node


def build_graph():
    """
    Build and compile the LangGraph workflow.

    The graph structure:
    1. Start -> RAG retrieval node (fetches knowledge base context)
    2. RAG node -> agent node
    3. Agent node -> conditional edges (tools/agent/end)
    4. Tools node -> agent node (loop back for continued conversation)

    Returns:
        Compiled LangGraph ready for invocation
    """
    graph = StateGraph(AgentState)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "rag_retrieval")
    graph.add_edge("rag_retrieval", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "agent": "agent", "end": END},
    )
    graph.add_edge("tools", "agent")
    return graph.compile()
