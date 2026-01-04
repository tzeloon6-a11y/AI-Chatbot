"""
Heritage Archive Search Agent - LangChain 1.0 with Chain-of-Thought.

This agent implements intent classification, query generation, and chain-of-thought
reasoning to automatically try alternative search strategies when needed.
"""

import logging
from typing import List, Dict, Any, AsyncIterator, Optional
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage

from app.core.config import settings
from app.services.ai_search.tools import search_archives_db, read_archives_data

logger = logging.getLogger(__name__)



# Updated system prompt with clear structure based on Gemini best practices
SEARCH_AGENT_PROMPT = """
<role>
You are a heritage archive search assistant. You help users find cultural heritage materials from a Malaysian heritage database using intent classification and chain-of-thought reasoning.
Today's date: {today}
</role>

<intent_classification>
BEFORE calling any tools, classify user intent into ONE of these categories:

| Intent | Description | Action |
|--------|-------------|--------|
| HERITAGE_SEARCH | User wants heritage materials (batik, crafts, temples, etc.) | Use search tools |
| GREETING | Hello, hi, thanks, how are you | Respond warmly, NO tools |
| UNCLEAR | Vague queries (why, huh, show me something) | Ask clarification, NO tools |
| UNRELATED | Non-heritage topics (weather, news, jokes) | Politely decline, NO tools |

CRITICAL: Only call tools for HERITAGE_SEARCH intent.
</intent_classification>

<response_by_intent>
GREETING → "Hello! I'm here to help you search our heritage archive. What cultural materials would you like to explore?"

UNCLEAR → "Could you provide more details? For example, specify a type (batik, crafts), location (Penang, Kelantan), or time period."

UNRELATED → "I can only help search for heritage materials like traditional crafts, cultural artifacts, and historical documents. What heritage items interest you?"

HERITAGE_SEARCH → Proceed to tool selection below.
</response_by_intent>

<tool_selection>
You have TWO tools for HERITAGE_SEARCH:

1. **search_archives_db** - Semantic AI search (use FIRST)
   - For descriptive queries: "find batik textiles", "traditional Kelantan crafts"
   - Returns similarity-ranked results
   
2. **read_archives_data** - Database filtering (use as FALLBACK or for browsing)
   - For metadata queries: "show all videos", "list by tag", "recently added"
   - Filter options: media_type, tag, title, date_from, date_to
   - For browsing: "what archives do you have?"

DECISION FLOW:
- Semantic query (find, show me, looking for) → search_archives_db FIRST
- Metadata/browse query (list, filter, all videos) → read_archives_data
- Zero results from search_archives_db → Try read_archives_data as fallback
</tool_selection>

<chain_of_thought>
When search_archives_db returns ZERO results, use this fallback strategy:

Step 1: Extract 2-3 key terms from user query
   Example: "sabah culture" → ["sabah", "culture", "heritage"]

Step 2: Try read_archives_data with each key term
   - First: filter_by="tag", filter_value="sabah"
   - Then: filter_by="title", filter_value="sabah"
   - Then: broader term like "culture" or "heritage"

Step 3: RELEVANCE REVIEW (CRITICAL!)
   Before showing ANY results to the user, you MUST:
   - Read each result's title, description, and tags
   - Ask: "Does this actually relate to what the user asked for?"
   - ONLY include materials that are genuinely relevant
   - EXCLUDE results that don't match semantically (e.g., user asked for "Sabah" but result is about "Johor")

Step 4: Return relevant findings with explanation
   - If relevant items found: "I found these through metadata browsing: [results]"
   - If nothing relevant: "I couldn't find archives matching your query."

NEVER show irrelevant results just because they exist in the database.
</chain_of_thought>

<examples>
USER: "hi" → GREETING → Respond with welcome message, NO tools

USER: "batik from Kelantan"
→ HERITAGE_SEARCH
→ search_archives_db(query="traditional Kelantan batik textiles")
→ If 0 results: read_archives_data(filter_by="tag", filter_value="kelantan")
→ Review: Are these actually about batik? Only show relevant ones.

USER: "show me all videos"
→ HERITAGE_SEARCH (metadata query)
→ read_archives_data(filter_by="media_type", filter_value="video", limit=20)

USER: "what's the weather?"
→ UNRELATED → Politely decline, NO tools
</examples>

<critical_rules>
DO:
✓ Classify intent FIRST before any action
✓ Use search_archives_db for semantic queries
✓ ALWAYS review results for relevance before showing to user
✓ Try read_archives_data fallback when semantic search fails
✓ Be honest when nothing relevant is found

DON'T:
✗ Call tools for greetings, unclear, or unrelated queries
✗ Show results that don't match user's request
✗ Return irrelevant archives just because they exist
✗ Skip the relevance review step
</critical_rules>
"""



class ArchiveSearchAgentV2:
    """
    Heritage archive search agent with intent classification and chain-of-thought reasoning.
    
    Features:
    - Intent classification (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
    - Single focused query generation
    - Chain-of-thought reasoning for automatic fallback strategies
    - Multi-tool orchestration (semantic search + metadata browsing)
    - Structured output for search results
    - Text responses for non-search intents
    
    Available Tools:
    1. search_archives_db: Semantic vector search for finding similar archives
    2. read_archives_data: Read-only metadata filtering and browsing (no write operations)
    """
    
    def __init__(self):
        logger.info("Initializing ArchiveSearchAgentV2 with chain-of-thought reasoning (LangChain 1.0)")
        
        # Initialize Gemini model
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=settings.GOOGLE_GENAI_API_KEY,
            temperature=0.2,  # Lower for focused query generation
        )
        
        # Tools: search_archives_db (vector search) + read_archives_data (metadata filtering)
        self.tools = [search_archives_db, read_archives_data]
        logger.info(f"Configured with {len(self.tools)} tool(s): {[tool.name for tool in self.tools]}")
        
        # Memory for conversation persistence
        self.memory = InMemorySaver()
        
        # Get current date/time for the system prompt
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create agent with chain-of-thought reasoning
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=SEARCH_AGENT_PROMPT.format(today=today),
            # checkpointer=self.memory,
        )
        logger.info("ArchiveSearchAgentV2 initialized with chain-of-thought multi-tool reasoning")
    
    def search(
        self, 
        user_query: str, 
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synchronous search returning structured archive data or text message.
        
        Args:
            user_query: User's search query
            thread_id: Optional conversation thread ID
            
        Returns:
            For HERITAGE_SEARCH intent:
            {
                "archives": [...],  # Structured archive list
                "total": int,        # Total count
                "query": str         # Echo of user query
            }
            
            For non-search intents (UNCLEAR, UNRELATED, GREETING):
            {
                "message": str,      # Text response
                "archives": [],      # Empty
                "total": 0,          # Zero
                "query": str         # Echo of user query
            }
        """
        thread_id = thread_id or "default"
        logger.info(f"Search: '{user_query}' (thread={thread_id})")
        
        try:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Invoke agent
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": user_query}]},
                config=config
            )
            
            # Check if agent returned text message (non-search intent)
            text_message = self._extract_text_message(result)
            if text_message:
                logger.info(f"Non-search intent detected: {text_message[:50]}...")
                return {
                    "message": text_message,
                    "archives": [],
                    "total": 0,
                    "query": user_query
                }
            
            # Extract archives from tool artifacts
            archives = self._extract_archives(result)
            
            logger.info(f"Found {len(archives)} archives")
            
            return {
                "archives": archives,
                "total": len(archives),
                "query": user_query
            }
            
        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            raise
    
    async def search_stream(
        self, 
        user_query: str,
        thread_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streaming search with progressive updates and intent detection.
        
        Yields:
            - {"type": "searching", "query": str}  # Agent is processing
            - {"type": "results", "archives": [...], "total": int}  # Results found
            - {"type": "message", "message": str}  # Text response (non-search)
            - {"type": "done", "archives": [...], "total": int}  # Completion signal
        """
        thread_id = thread_id or "default"
        logger.info(f"Stream search: '{user_query}' (thread={thread_id})")
        
        try:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Immediately acknowledge search started
            yield {
                "type": "searching",
                "query": user_query
            }
            
            all_archives: List[Dict[str, Any]] = []
            text_message: Optional[str] = None
            
            # Stream agent execution
            async for event in self.agent.astream(
                {"messages": [{"role": "user", "content": user_query}]},
                config=config,
                stream_mode="values"
            ):
                # Check for text message (non-search intent)
                if not text_message:
                    msg = self._extract_text_message(event)
                    if msg:
                        text_message = msg
                        yield {
                            "type": "message",
                            "message": text_message
                        }
                        continue
                
                # Extract archives from any tool messages
                archives = self._extract_archives(event)
                
                if archives and len(archives) > len(all_archives):
                    all_archives = archives
                    # Send incremental results
                    yield {
                        "type": "results",
                        "archives": archives,
                        "total": len(archives)
                    }
            
            # Final results
            yield {
                "type": "done",
                "archives": all_archives,
                "total": len(all_archives)
            }
            
            logger.info(f"Stream complete: {len(all_archives)} archives, text_message={bool(text_message)}")
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield {
                "type": "error",
                "message": str(e)
            }
    
    def _extract_text_message(self, result: Dict[str, Any]) -> Optional[str]:
        """
        Extract text message from agent response (for non-search intents).
        
        Returns text message if agent responded without calling search tool,
        None otherwise (indicating HERITAGE_SEARCH intent).
        """
        messages = result.get("messages", [])
        
        # Check if last message is from AI and contains no tool calls
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                # If AI message has no tool calls and no tool artifacts in history,
                # it's a text response (non-search intent)
                has_tool_calls = hasattr(last_msg, "tool_calls") and last_msg.tool_calls
                has_tool_artifacts = any(
                    hasattr(msg, "artifact") and msg.artifact
                    for msg in messages
                )
                
                if not has_tool_calls and not has_tool_artifacts:
                    content = last_msg.content
                    
                    # Handle multimodal content format from Gemini
                    # Content can be a list of dicts like [{'type': 'text', 'text': '...'}]
                    if isinstance(content, list):
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        content = " ".join(text_parts) if text_parts else ""
                    
                    # Filter out tool code that was incorrectly returned as text
                    # This happens when the model outputs code instead of calling tools
                    tool_code_patterns = [
                        "tool_code",
                        "default_api.",
                        "search_archives_db(",
                        "read_archives_data(",
                        "print(default_api",
                    ]
                    
                    # If content contains tool code patterns, don't return it as a message
                    if any(pattern in content for pattern in tool_code_patterns):
                        logger.warning(f"Tool code detected in content, filtering out: {content}")
                        return None
                    
                    # Pure text response
                    return content
        
        return None
    
    def _extract_archives(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract archive data from agent result."""
        archives: Dict[str, Dict[str, Any]] = {}
        
        messages = result.get("messages", [])
        
        for msg in messages:
            # Check for tool message with artifact
            if hasattr(msg, "artifact") and msg.artifact:
                if isinstance(msg.artifact, list):
                    for archive in msg.artifact:
                        if isinstance(archive, dict) and "id" in archive:
                            archives[archive["id"]] = archive
        
        return list(archives.values())


# Singleton instance
_agent_instance = None


def get_archive_search_agent() -> ArchiveSearchAgentV2:
    """Get or create the agent singleton."""
    global _agent_instance
    if _agent_instance is None:
        logger.info("Creating new ArchiveSearchAgentV2 singleton")
        _agent_instance = ArchiveSearchAgentV2()
    return _agent_instance
