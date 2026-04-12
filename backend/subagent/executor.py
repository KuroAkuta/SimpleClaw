"""Subagent execution engine."""

import asyncio
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
import queue
import threading

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from subagent.config import SubagentConfig

logger = logging.getLogger(__name__)


class SubagentStatus(Enum):
    """Status of a subagent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentResult:
    """Result of a subagent execution.

    Attributes:
        task_id: Unique identifier for this execution.
        status: Current status of the execution.
        result: The final result message (if completed).
        error: Error message (if failed).
        started_at: When execution started.
        completed_at: When execution completed.
        messages: List of messages generated during execution.
    """

    task_id: str
    status: SubagentStatus
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    messages: list[dict[str, Any]] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.messages is None:
            self.messages = []


# Global storage for background task results
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()

# Storage for subagent tool call history (for async tasks)
_subagent_tool_history: dict[str, list[dict]] = {}
_subagent_tool_history_lock = threading.Lock()

# Thread pool for background task scheduling and orchestration
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")

# Thread pool for actual subagent execution (with timeout support)
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")


def add_subagent_tool_event(task_id: str, tool_name: str, status: str, args: dict = None, result: str = None):
    """Add a tool execution event to the subagent's history."""
    with _subagent_tool_history_lock:
        if task_id not in _subagent_tool_history:
            _subagent_tool_history[task_id] = []
        _subagent_tool_history[task_id].append({
            "tool_name": tool_name,
            "status": status,  # pending, running, completed, failed
            "args": args or {},
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })


def get_subagent_tool_history(task_id: str) -> list[dict]:
    """Get the tool execution history for a subagent task."""
    with _subagent_tool_history_lock:
        return list(_subagent_tool_history.get(task_id, []))


def _filter_tools(
    all_tools: list,
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list:
    """Filter tools based on subagent configuration.

    Args:
        all_tools: List of all available tools.
        allowed: Optional allowlist of tool names. If provided, only these tools are included.
        disallowed: Optional denylist of tool names. These tools are always excluded.

    Returns:
        Filtered list of tools.
    """
    filtered = all_tools

    # Apply allowlist if specified
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [t for t in filtered if t.name in allowed_set]

    # Apply denylist
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [t for t in filtered if t.name not in disallowed_set]

    return filtered


class SubagentExecutor:
    """Executor for running subagents."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list,
        parent_model: Any = None,
        trace_id: str | None = None,
    ):
        """Initialize the executor.

        Args:
            config: Subagent configuration.
            tools: List of all available tools (will be filtered).
            parent_model: The parent agent's model for inheritance.
            trace_id: Trace ID for distributed tracing.
        """
        self.config = config
        self.parent_model = parent_model
        # Generate trace_id if not provided (for top-level calls)
        self.trace_id = trace_id or str(uuid.uuid4())[:8]

        # Filter tools based on config
        self.tools = _filter_tools(
            tools,
            config.tools,
            config.disallowed_tools,
        )

        logger.info(f"[trace={self.trace_id}] SubagentExecutor initialized: {config.name} with {len(self.tools)} tools")

    def _build_initial_state(self, task: str) -> dict[str, Any]:
        """Build the initial state for agent execution.

        Args:
            task: The task description.

        Returns:
            Initial state dictionary.
        """
        return {
            "messages": [HumanMessage(content=task)],
        }

    def _create_agent_graph(self):
        """Create the agent graph for subagent execution.

        Returns:
            Compiled LangGraph ready for invocation.
        """
        from langgraph.graph import StateGraph, START, END
        from langgraph.graph import StateGraph, START, END
        from langchain_core.messages import SystemMessage
        from typing import Annotated
        import operator

        # Define state schema with proper message accumulation
        class SubagentState(dict):
            messages: Annotated[list, operator.add]
            turn_count: int = 0

        from config.settings import settings
        from services.model_service import get_model_with_tools

        def agent_node(state: SubagentState) -> dict:
            """Agent node that processes the task."""
            # Build system message
            system_message = SystemMessage(content=self.config.system_prompt)
            messages = [system_message] + state["messages"]

            # Get model with filtered tools
            model_with_tools = get_model_with_tools()
            # Bind filtered tools to model
            if self.tools:
                model_with_tools = model_with_tools.bind_tools(self.tools)

            response = model_with_tools.invoke(messages)

            new_turn_count = state.get("turn_count", 0) + 1
            return {
                "messages": [response],
                "turn_count": new_turn_count,
            }

        def tool_node(state: SubagentState) -> dict:
            """Tool node that executes pending tool calls."""
            last_message = state["messages"][-1]

            if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
                return {"messages": []}

            # Build tool lookup
            tools_by_name = {t.name: t for t in self.tools}

            results = []
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})

                if tool_name not in tools_by_name:
                    result = f"Error: Unknown tool '{tool_name}'"
                    add_subagent_tool_event(self.trace_id, tool_name, "failed", tool_args, result)
                else:
                    try:
                        tool_func = tools_by_name[tool_name]
                        result = tool_func.invoke(tool_args)
                        add_subagent_tool_event(self.trace_id, tool_name, "completed", tool_args, str(result)[:500])
                    except Exception as e:
                        result = f"Error: {e}"
                        add_subagent_tool_event(self.trace_id, tool_name, "failed", tool_args, result)

                results.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )

            return {"messages": results}

        def should_continue(state: SubagentState) -> str:
            """Determine the next node."""
            # Check max turns
            if state.get("turn_count", 0) >= self.config.max_turns:
                return "end"

            last_message = state["messages"][-1]
            has_tool_calls = hasattr(last_message, "tool_calls") and last_message.tool_calls

            if has_tool_calls:
                return "tools"

            if isinstance(last_message, ToolMessage):
                return "agent"

            return "end"

        # Build graph
        graph = StateGraph(SubagentState)
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

    def _execute_sync(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Execute a task synchronously.

        Args:
            task: The task description for the subagent.
            result_holder: Optional pre-created result object to update during execution.

        Returns:
            SubagentResult with the execution result.
        """
        if result_holder is not None:
            result = result_holder
            # Use task_id from result_holder for tool history tracking
            self.trace_id = result.task_id
        else:
            task_id = str(uuid.uuid4())[:8]
            result = SubagentResult(
                task_id=task_id,
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )
            self.trace_id = task_id

        try:
            agent_graph = self._create_agent_graph()
            state = self._build_initial_state(task)

            logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} starting execution with max_turns={self.config.max_turns}")

            # Run the graph
            config = {"recursion_limit": self.config.max_turns * 2}
            final_state = agent_graph.invoke(state, config=config)

            logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} completed execution")
            print(f"[DEBUG] final_state: {final_state}")

            # Extract final response
            result.result = "No response generated"  # Default fallback
            if final_state and "messages" in final_state:
                messages = final_state["messages"]
                # Find last AI message
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        content = msg.content
                        if isinstance(content, str):
                            result.result = content
                        elif isinstance(content, list):
                            # Extract text from content blocks
                            text_parts = []
                            for block in content:
                                if isinstance(block, str):
                                    text_parts.append(block)
                                elif isinstance(block, dict) and block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                            result.result = "\n".join(text_parts) if text_parts else "No text content"
                        else:
                            result.result = str(content)
                        break
                else:
                    result.result = "No AI message found"
            else:
                result.result = "No final state"

            result.status = SubagentStatus.COMPLETED
            result.completed_at = datetime.now()

        except Exception as e:
            logger.exception(f"[trace={self.trace_id}] Subagent {self.config.name} execution failed")
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

        return result

    def execute(self, task: str, result_holder: SubagentResult | None = None) -> SubagentResult:
        """Execute a task synchronously.

        This is the main entry point for synchronous subagent execution.

        Args:
            task: The task description for the subagent.
            result_holder: Optional pre-created result object to update during execution.

        Returns:
            SubagentResult with the execution result.
        """
        return self._execute_sync(task, result_holder)

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Start a task execution in the background.

        Args:
            task: The task description for the subagent.
            task_id: Optional task ID to use. If not provided, a random UUID will be generated.

        Returns:
            Task ID that can be used to check status later.
        """
        # Use provided task_id or generate a new one
        if task_id is None:
            task_id = str(uuid.uuid4())[:8]

        # Create initial pending result
        result = SubagentResult(
            task_id=task_id,
            status=SubagentStatus.PENDING,
        )

        logger.info(f"[trace={self.trace_id}] Subagent {self.config.name} starting async execution, task_id={task_id}, timeout={self.config.timeout_seconds}s")

        with _background_tasks_lock:
            _background_tasks[task_id] = result

        # Submit to scheduler pool
        def run_task():
            with _background_tasks_lock:
                _background_tasks[task_id].status = SubagentStatus.RUNNING
                _background_tasks[task_id].started_at = datetime.now()
                result_holder = _background_tasks[task_id]

            try:
                # Submit execution to execution pool with timeout
                execution_future: Future = _execution_pool.submit(self._execute_sync, task, result_holder)
                try:
                    # Wait for execution with timeout
                    exec_result = execution_future.result(timeout=self.config.timeout_seconds)
                    with _background_tasks_lock:
                        _background_tasks[task_id].status = exec_result.status
                        _background_tasks[task_id].result = exec_result.result
                        _background_tasks[task_id].error = exec_result.error
                        _background_tasks[task_id].completed_at = datetime.now()
                        _background_tasks[task_id].messages = exec_result.messages
                except FuturesTimeoutError:
                    logger.error(f"[trace={self.trace_id}] Subagent {self.config.name} execution timed out after {self.config.timeout_seconds}s")
                    with _background_tasks_lock:
                        if _background_tasks[task_id].status == SubagentStatus.RUNNING:
                            _background_tasks[task_id].status = SubagentStatus.TIMED_OUT
                            _background_tasks[task_id].error = f"Execution timed out after {self.config.timeout_seconds} seconds"
                            _background_tasks[task_id].completed_at = datetime.now()
                    # Signal cooperative cancellation
                    result_holder.cancel_event.set()
                    execution_future.cancel()
            except Exception as e:
                logger.exception(f"[trace={self.trace_id}] Subagent {self.config.name} async execution failed")
                with _background_tasks_lock:
                    _background_tasks[task_id].status = SubagentStatus.FAILED
                    _background_tasks[task_id].error = str(e)
                    _background_tasks[task_id].completed_at = datetime.now()

        _scheduler_pool.submit(run_task)
        return task_id


MAX_CONCURRENT_SUBAGENTS = 3


def request_cancel_background_task(task_id: str) -> None:
    """Signal a running background task to stop.

    Sets the cancel_event on the task, which is checked cooperatively
    by the execution loop.

    Args:
        task_id: The task ID to cancel.
    """
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is not None:
            result.cancel_event.set()
            logger.info("Requested cancellation for background task %s", task_id)


def get_background_task_result(task_id: str) -> SubagentResult | None:
    """Get the result of a background task.

    Args:
        task_id: The task ID returned by execute_async.

    Returns:
        SubagentResult if found, None otherwise.
    """
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    """List all background tasks.

    Returns:
        List of all SubagentResult instances.
    """
    with _background_tasks_lock:
        return list(_background_tasks.values())


def cleanup_background_task(task_id: str) -> None:
    """Remove a completed task from background tasks.

    Should be called after retrieving the result to prevent memory leaks.

    Args:
        task_id: The task ID to remove.
    """
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is None:
            logger.debug("Requested cleanup for unknown background task %s", task_id)
            return

        # Only clean up tasks that are in a terminal state to avoid races
        is_terminal_status = result.status in {
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.CANCELLED,
            SubagentStatus.TIMED_OUT,
        }
        if is_terminal_status or result.completed_at is not None:
            del _background_tasks[task_id]
            logger.debug("Cleaned up background task: %s", task_id)
