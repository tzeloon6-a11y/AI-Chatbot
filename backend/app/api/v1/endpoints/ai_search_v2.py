"""
Clean AI Search Endpoint - Structured Responses Only.

Returns ONLY structured archive data, NO text responses.
Perfect for modern chat UX with immediate feedback.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json

from app.services.ai_search.agent_v2 import get_archive_search_agent


router = APIRouter()


class SearchRequest(BaseModel):
    """Request model for AI search."""
    query: str = Field(..., min_length=1, description="Search query")
    thread_id: str | None = Field(None, description="Optional conversation thread ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "batik",
                "thread_id": "user-123"
            }
        }


class ArchiveResult(BaseModel):
    """Structured archive result."""
    id: str
    title: str
    description: str | None = None
    media_types: List[str]
    dates: List[str] | None = None
    tags: List[str] | None = None
    file_uris: List[str] | None = None
    storage_paths: List[str] | None = None
    created_at: str
    updated_at: str | None = None
    similarity: float | None = None


class SearchResponse(BaseModel):
    """Search response supporting both results and text messages."""
    response_type: str = Field(..., description="Type of response: 'results' or 'message'")
    archives: List[ArchiveResult] = Field(default=[], description="Archive results (empty if response_type='message')")
    total: int = Field(default=0, description="Total number of archives found")
    query: str = Field(..., description="Echo of user query")
    message: str | None = Field(None, description="Text message for non-search intents or no results")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "response_type": "results",
                    "archives": [
                        {
                            "id": "uuid-here",
                            "title": "Traditional Batik Patterns",
                            "description": "Collection of batik patterns",
                            "media_types": ["image"],
                            "dates": ["2024-01-15T00:00:00Z"],
                            "tags": ["batik", "textile"],
                            "file_uris": ["https://storage.url/file.jpg"],
                            "created_at": "2024-01-15T10:00:00Z",
                            "similarity": 0.85
                        }
                    ],
                    "total": 1,
                    "query": "batik",
                    "message": None
                },
                {
                    "response_type": "message",
                    "archives": [],
                    "total": 0,
                    "query": "hello",
                    "message": "Hello! I'm here to help you search our heritage archive..."
                }
            ]
        }


@router.post("/ai-search", response_model=SearchResponse)
async def ai_search(request: SearchRequest):
    """
    AI-powered archive search with intent classification.
    
    **Intent Classification:**
    - HERITAGE_SEARCH: Returns structured archive results (response_type="results")
    - UNCLEAR/UNRELATED/GREETING: Returns text message (response_type="message")
    
    **Response Formats:**
    
    1. **Search Results** (response_type="results"):
       - archives: Array of matching archives
       - total: Count of results
       - query: Echo of user query
       - message: null
    
    2. **Text Message** (response_type="message"):
       - archives: [] (empty)
       - total: 0
       - query: Echo of user query
       - message: Text response (clarification, greeting, or polite decline)
    
    **Features:**
    - Intent classification (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
    - Focused single query generation
    - Automatic search refinement with retry (max 3 attempts)
    - Thread-based conversation persistence
    
    **Examples:**
    ```
    POST /ai-search
    {"query": "batik", "thread_id": "user-123"}
    
    Response:
    {
      "response_type": "results",
      "archives": [...],
      "total": 5,
      "query": "batik",
      "message": null
    }
    
    POST /ai-search
    {"query": "hello", "thread_id": "user-123"}
    
    Response:
    {
      "response_type": "message",
      "archives": [],
      "total": 0,
      "query": "hello",
      "message": "Hello! I'm here to help you search our heritage archive..."
    }
    ```
    """
    try:
        # Get agent
        agent = get_archive_search_agent()
        
        # Perform search
        result = agent.search(
            user_query=request.query,
            thread_id=request.thread_id
        )
        
        # Check if agent returned a text message (non-search intent)
        text_message = result.get("message")
        archives = result.get("archives", [])
        total = result.get("total", 0)
        
        if text_message:
            # Non-search intent (UNCLEAR, UNRELATED, GREETING)
            response_data = {
                "response_type": "message",
                "archives": [],
                "total": 0,
                "query": request.query,
                "message": text_message
            }
        elif total > 0:
            # Search results found
            response_data = {
                "response_type": "results",
                "archives": archives,
                "total": total,
                "query": request.query,
                "message": None
            }
        else:
            # No results found after retries
            response_data = {
                "response_type": "message",
                "archives": [],
                "total": 0,
                "query": request.query,
                "message": "I couldn't find relevant heritage materials matching your query. Try describing what you're looking for in different words, or browse our collection for inspiration."
            }
        
        return SearchResponse(**response_data)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/ai-search/stream")
async def ai_search_stream(request: SearchRequest):
    """
    Streaming AI search with intent classification and progressive updates.
    
    Returns Server-Sent Events (SSE) supporting both results and text messages:
    
    **Event Types:**
    - `query_received`: Immediate acknowledgment
      ```json
      {"type": "query_received", "query": "batik", "timestamp": "..."}
      ```
    
    - `searching`: Agent is generating queries
      ```json
      {"type": "searching", "query": "batik"}
      ```
    
    - `results`: Progressive results (sent as archives are found)
      ```json
      {"type": "results", "archives": [...], "total": 5}
      ```
    
    - `message`: Text response for non-search intents
      ```json
      {"type": "message", "message": "Hello! I'm here to help..."}
      ```
    
    - `done`: Final completion
      ```json
      {"type": "done", "response_type": "results", "archives": [...], "total": 5}
      ```
      or
      ```json
      {"type": "done", "response_type": "message", "message": "...", "archives": [], "total": 0}
      ```
    
    - `error`: Error occurred
      ```json
      {"type": "error", "message": "..."}
      ```
    
    **Frontend should:**
    1. Listen for `query_received` → clear input, show user message
    2. Listen for `searching` → show loading indicator
    3. Listen for `results` → progressively display archives
    4. Listen for `message` → display text response
    5. Listen for `done` → finalize UI with response_type, hide loading
    """
    try:
        # Get agent
        agent = get_archive_search_agent()
        
        async def event_generator():
            """Generate SSE events."""
            try:
                # IMMEDIATE: Acknowledge query received
                yield f"data: {json.dumps({
                    'type': 'query_received',
                    'query': request.query,
                    'thread_id': request.thread_id,
                    'timestamp': datetime.now().isoformat()
                })}\\n\\n"
                
                # Stream agent results
                all_archives: List[Dict[str, Any]] = []
                text_message: Optional[str] = None
                
                async for update in agent.search_stream(
                    user_query=request.query,
                    thread_id=request.thread_id
                ):
                    # Forward all events
                    yield f"data: {json.dumps(update)}\\n\\n"
                    
                    # Track archives and messages
                    if update.get("type") == "done":
                        all_archives = update.get("archives", [])
                    elif update.get("type") == "message":
                        text_message = update.get("message")
                
                # Send completion with appropriate response_type
                final_event = {
                    "type": "complete",
                    "query": request.query
                }
                
                if text_message:
                    # Non-search intent
                    final_event.update({
                        "response_type": "message",
                        "message": text_message,
                        "archives": [],
                        "total": 0
                    })
                elif len(all_archives) > 0:
                    # Search results
                    final_event.update({
                        "response_type": "results",
                        "archives": all_archives,
                        "total": len(all_archives),
                        "message": None
                    })
                else:
                    # No results after retries
                    final_event.update({
                        "response_type": "message",
                        "message": "I couldn't find relevant heritage materials matching your query. Try describing what you're looking for in different words, or browse our collection for inspiration.",
                        "archives": [],
                        "total": 0
                    })
                
                yield f"data: {json.dumps(final_event)}\\n\\n"
                
            except Exception as e:
                # Error event
                yield f"data: {json.dumps({
                    'type': 'error',
                    'message': str(e)
                })}\\n\\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Streaming search failed: {str(e)}"
        )
