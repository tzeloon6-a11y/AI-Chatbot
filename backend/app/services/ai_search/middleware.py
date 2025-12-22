"""
Custom middleware for search refinement with retry logic.

Implements LangChain middleware pattern to intercept search tool calls
and automatically refine queries based on result quality.
"""

import logging
from typing import Callable

from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command
from typing_extensions import NotRequired

logger = logging.getLogger(__name__)


class SearchRefinementState(AgentState):
    """
    Custom state schema for search refinement tracking.
    Extends AgentState (TypedDict) to add search-specific fields.
    
    Note: In LangChain 1.0, AgentState must be a TypedDict, not a Pydantic model.
    Access fields using dict syntax: state["field_name"]
    """
    # Number of search attempts made for current query
    search_attempt_count: NotRequired[int]
    
    # Original user query before any refinement
    original_user_query: NotRequired[str]
    
    # List of all queries tried (including original and refinements)
    previous_queries_tried: NotRequired[list[str]]
    
    # Best results found so far (highest similarity scores)
    best_results: NotRequired[list[dict]]


# Configuration constants
MAX_ATTEMPTS = 3
MIN_SIMILARITY_THRESHOLD = 0.4


def _evaluate_results(archives: list[dict], min_similarity_threshold: float) -> bool:
    """
    Evaluate if results are good enough to return to user.
    
    Criteria:
    - Results must not be empty
    - At least one result must have similarity >= min_similarity_threshold
    
    Args:
        archives: List of archive dictionaries from search tool
        min_similarity_threshold: Minimum acceptable similarity score
        
    Returns:
        True if results are acceptable, False otherwise
    """
    if not archives:
        logger.debug("Evaluation: No results found")
        return False  # No results - need refinement
    
    # Check if at least one result has good similarity
    # Handle None values by treating them as 0
    good_results = [
        archive for archive in archives
        if (archive.get("similarity") or 0) >= min_similarity_threshold
    ]
    
    has_good_results = len(good_results) > 0
    logger.debug(
        f"Evaluation: {len(good_results)}/{len(archives)} results above threshold "
        f"(>={min_similarity_threshold})"
    )
    
    return has_good_results


@wrap_tool_call
def search_refinement_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """
    Middleware that intercepts search_archives_db tool calls and evaluates
    result quality. If results are poor (empty or low similarity), it returns
    a message asking the agent to refine the query.
    
    This implements the retry logic using LangChain's @wrap_tool_call decorator,
    which is the recommended pattern for intercepting tool execution.
    
    Configuration:
        MAX_ATTEMPTS: Maximum number of search attempts before giving up (default: 3)
        MIN_SIMILARITY_THRESHOLD: Minimum similarity score to consider results acceptable (default: 0.4)
    
    State Tracking:
        Uses SearchRefinementState to track:
        - search_attempt_count: Number of attempts made
        - original_user_query: The first query from user
        - previous_queries_tried: All queries attempted
        - best_results: Best results found so far
    
    Behavior:
        1. Intercepts calls to search_archives_db
        2. Executes the search and evaluates results
        3. If results are good: Returns them to agent
        4. If results are poor and attempts < max: Returns refinement request
        5. If max attempts reached: Returns best results found
        
    Args:
        request: ToolCallRequest containing tool_call info and state
        handler: Function to execute the actual tool
        
    Returns:
        ToolMessage with results or refinement request
    """
    tool_name = request.tool_call.get("name")
    
    # Only intercept search_archives_db calls
    if tool_name != "search_archives_db":
        logger.debug(f"Skipping interception for tool: {tool_name}")
        return handler(request)
    
    # Get current state (state is a dict, not an object)
    state = request.state
    attempt_count = state.get("search_attempt_count", 0)
    original_query = state.get("original_user_query", "")
    previous_queries = state.get("previous_queries_tried", [])
    best_results = state.get("best_results", [])
    
    current_query = request.tool_call.get("args", {}).get("query", "")
    
    logger.info(
        f"Intercepted search_archives_db call (attempt {attempt_count + 1}/{MAX_ATTEMPTS}): "
        f"query='{current_query}'"
    )
    
    # Record this as first query if not set
    if not original_query:
        original_query = current_query
    
    # Execute the search
    try:
        result = handler(request)
        
        # Parse result - expect (message_str, archives_list) tuple
        if isinstance(result, ToolMessage):
            # Already a ToolMessage (error case or direct return)
            return result
        
        if isinstance(result, tuple) and len(result) == 2:
            message_str, archives = result
        else:
            # Unexpected format - return as-is
            logger.warning(f"Unexpected tool result format: {type(result)}")
            return result
        
    except Exception as e:
        logger.error(f"Error executing search tool: {e}")
        return ToolMessage(
            content=f"Search failed: {str(e)}",
            tool_call_id=request.tool_call["id"]
        )
    
    # Evaluate results
    results_are_good = _evaluate_results(archives, MIN_SIMILARITY_THRESHOLD)
    
    # Update best results if these are better
    if archives and (not best_results or 
                    max(((a.get("similarity") or 0) for a in archives), default=0) >
                    max(((b.get("similarity") or 0) for b in best_results), default=0)):
        best_results = archives
    
    # Update tracking
    new_attempt_count = attempt_count + 1
    new_previous_queries = previous_queries + [current_query]
    
    # Decision logic
    if results_are_good:
        logger.info(f"✓ Results acceptable (attempt {new_attempt_count})")
        return ToolMessage(
            content=message_str,
            tool_call_id=request.tool_call["id"]
        )
    
    if new_attempt_count >= MAX_ATTEMPTS:
        logger.info(f"⚠ Max attempts reached ({MAX_ATTEMPTS}), returning best results")
        if best_results:
            return ToolMessage(
                content=f"Found {len(best_results)} results after {new_attempt_count} attempts.",
                tool_call_id=request.tool_call["id"]
            )
        else:
            return ToolMessage(
                content=f"No good results found after {new_attempt_count} attempts. Try a different query.",
                tool_call_id=request.tool_call["id"]
            )
    
    # Results are poor and we can retry
    logger.info(f"⟳ Results poor, requesting refinement (attempt {new_attempt_count}/{MAX_ATTEMPTS})")
    
    refinement_message = (
        f"The search query '{current_query}' returned {len(archives)} results, "
        f"but none had high enough relevance (similarity < {MIN_SIMILARITY_THRESHOLD}). "
        f"\n\nPrevious queries tried: {', '.join(previous_queries)}\n\n"
        f"Please refine the query with different keywords or phrasing. "
        f"Consider: more specific terms, related concepts, alternative terminology."
    )
    
    return ToolMessage(
        content=refinement_message,
        tool_call_id=request.tool_call["id"]
    )

