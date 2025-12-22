"""AI Search endpoint for archive search using LangChain agent."""

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from app.services.ai_search import get_archive_search_agent


router = APIRouter()


class SearchRequest(BaseModel):
    """Request model for AI search."""
    query: str
    thread_id: str | None = None  # Optional conversation thread ID for persistence
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "I want batik",
                "thread_id": "user-123-session"
            }
        }


class SearchResponse(BaseModel):
    """Response model for AI search."""
    message: str
    archives: list[Dict[str, Any]]
    metadata: Dict[str, Any] | None = None  # Search metadata (queries, stats, etc.)
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Found 3 traditional batik archives matching your request.",
                "archives": [
                    {
                        "id": "uuid-here",
                        "title": "Traditional Batik Patterns",
                        "description": "Collection of batik patterns",
                        "summary": "Traditional Malaysian batik...",
                        "tags": ["batik", "textile"],
                        "media_types": ["image"],
                        "dates": ["2024-01-15T00:00:00Z"],
                        "storage_paths": ["path/to/file"],
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z",
                        "similarity": 0.85
                    }
                ],
                "metadata": {
                    "queries_made": ["batik patterns", "traditional textile"],
                    "total_archives": 3,
                    "tool_calls": 2,
                    "conversation_turn": 1
                }
            }
        }


@router.post("/ai-search", response_model=SearchResponse)
async def ai_search(request: SearchRequest):
    """
    AI-powered archive search using LangChain 1.0 agent with middleware.
    
    The agent automatically:
    1. Generates multiple diverse search queries (via MultiQueryMiddleware)
    2. Executes searches with error handling and retries (via ErrorHandlingMiddleware)
    3. Tracks conversation state and search history (via StateTrackingMiddleware)
    4. Manages context and trims messages (via DynamicPromptMiddleware)
    5. Persists conversation across requests (via MemorySaver checkpointing)
    
    Provide a thread_id to maintain conversation context across multiple requests.
    
    Example:
        Query: "I want batik"
        Middleware generates: ["batik patterns", "traditional Malaysian textile", "heritage fabric"]
        Returns: Deduplicated archives with metadata about the search process
    """
    try:
        # Validate query
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Query cannot be empty"
            )
        
        # Get agent instance
        agent = get_archive_search_agent()
        
        # Perform search with thread_id for conversation persistence
        result = agent.search(
            user_query=request.query,
            thread_id=request.thread_id
        )
        
        return SearchResponse(
            message=result["message"],
            archives=result["archives"],
            metadata=result.get("metadata")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI search failed: {str(e)}"
        )


@router.post("/ai-search/stream")
async def ai_search_stream(request: SearchRequest):
    """
    AI-powered archive search with streaming support.
    
    Streams the agent's progress in real-time as middleware processes:
    1. Multi-query generation and execution
    2. Error handling and retries
    3. State tracking and deduplication
    4. Context management
    
    Provide a thread_id to maintain conversation context across multiple requests.
    
    Returns Server-Sent Events (SSE) with:
    - query_received: Immediate acknowledgment with echoed query
    - processing: Agent is processing the query
    - message: Agent's reasoning and responses
    - tool_call: Tool execution notifications
    - archives: Found archive artifacts
    - final: Complete results with metadata
    - done: Stream completion signal
    """
    try:
        # Validate query
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Query cannot be empty"
            )
        
        # Get agent instance
        agent = get_archive_search_agent()
        
        async def event_generator():
            """Generate Server-Sent Events for streaming."""
            try:
                # IMMEDIATE: Send query received acknowledgment
                # This allows frontend to clear input and show user message immediately
                query_received_event = json.dumps({
                    "type": "query_received",
                    "query": request.query,
                    "thread_id": request.thread_id,
                    "timestamp": datetime.now().isoformat()
                })
                yield f"data: {query_received_event}\n\n"
                
                # Send processing started event
                processing_event = json.dumps({
                    "type": "processing",
                    "message": "Processing your query..."
                })
                yield f"data: {processing_event}\n\n"
                
                # Stream agent responses
                async for update in agent.search_stream(
                    user_query=request.query,
                    thread_id=request.thread_id
                ):
                    # Format as SSE
                    event_data = json.dumps(update)
                    yield f"data: {event_data}\n\n"
                
                # Send final done event
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
            except Exception as e:
                # Send error event
                error_data = json.dumps({
                    "type": "error",
                    "message": str(e)
                })
                yield f"data: {error_data}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable buffering in nginx
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI search streaming failed: {str(e)}"
        )
