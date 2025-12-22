"""
Heritage Archive Search Agent - LangChain 1.0 with Middleware.

This agent implements intent classification, query generation, and search refinement
with automatic retry logic via middleware.
"""

import logging
from typing import List, Dict, Any, AsyncIterator, Optional
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage

from app.core.config import settings
from app.services.ai_search.tools import search_archives_db, read_archives_data
from app.services.ai_search.middleware import search_refinement_middleware

logger = logging.getLogger(__name__)


# Updated system prompt with intent classification and refinement logic
SEARCH_AGENT_PROMPT = """You are a heritage archive search assistant with intent classification and database access.

WORKFLOW:
1. CLASSIFY user intent (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
2. If HERITAGE_SEARCH: Choose the appropriate tool based on query type
3. Call the selected tool with appropriate parameters
4. If tool returns a refinement request: Try a different approach or query
5. Return structured results or helpful message

INTENT CLASSIFICATION:
- HERITAGE_SEARCH: User looking for heritage materials (proceed to search)
  Examples: "batik", "traditional crafts", "wayang kulit videos", "Georgetown architecture"
  
- UNCLEAR: Query too vague or ambiguous (ask for clarification)
  Examples: "show me something", "what do you have?", "stuff", "things"
  
- UNRELATED: Not about heritage (politely decline)
  Examples: "what's the weather?", "how to cook rice?", "tell me a joke", "latest news"
  
- GREETING: Conversational/greeting messages (respond warmly, offer to help)
  Examples: "hello", "hi there", "how are you?", "thanks"

RESPONSE RULES BY INTENT:
- HERITAGE_SEARCH → Call search tool and return structured results
- UNCLEAR → "Could you please provide more details about what heritage materials you're looking for? For example, you could specify a type (batik, crafts, architecture), location, or time period."
- UNRELATED → "I can only help you search for heritage archive materials such as traditional crafts, cultural artifacts, historical documents, and cultural media. How can I assist you with heritage materials today?"
- GREETING → "Hello! I'm here to help you search our heritage archive. What cultural materials or historical items would you like to explore?"

QUERY GENERATION (for HERITAGE_SEARCH):
- Generate ONE focused query that captures core intent
- Be specific but not overly narrow
- Include key terms: object type, cultural context, location, time period
- Examples:
  * User: "I want batik from Kelantan" → Query: "traditional Kelantan batik textiles"
  * User: "show me wayang kulit videos" → Query: "wayang kulit shadow puppet performances videos"
  * User: "old Georgetown photos" → Query: "historical Georgetown heritage architecture photographs"

AVAILABLE TOOLS:
1. search_archives_db - Use for semantic vector search when user describes what they're looking for
2. read_archives_data - Use for browsing or filtering by specific metadata (tags, media types, dates)
   Examples of when to use read_archives_data:
   - "Show me all video archives" → read_archives_data(filter_by="media_type", filter_value="video")
   - "List archives with batik tag" → read_archives_data(filter_by="tag", filter_value="batik")
   - "What archives were created recently?" → read_archives_data(order_by="created_at", limit=10)

QUERY REFINEMENT (if tool requests it):
- The middleware will automatically handle retry logic (max 3 attempts)
- If tool returns a refinement message, analyze why previous queries didn't work
- Try different terminology, broader/narrower scope, or cultural synonyms
- DO NOT repeat previous queries
- Examples:
  * If "Kelantan batik" failed → Try "Malaysian batik textiles"
  * If "crafts" too broad → Try "traditional Malaysian handicrafts"
  * If "shadow puppets" failed → Try "wayang kulit traditional performance"

IMPORTANT:
- Middleware handles retry logic automatically - you just generate refined queries when asked
- Always call the tool with a SINGLE query string, not a list
- Return structured archive data for HERITAGE_SEARCH
- Return text messages for other intents
"""


class ArchiveSearchAgentV2:
    """
    Heritage archive search agent with intent classification and search refinement.
    
    Features:
    - Intent classification (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
    - Single focused query generation
    - Automatic search refinement via middleware (max 3 attempts)
    - Structured output for search results
    - Text responses for non-search intents
    
    Available Tools:
    1. search_archives_db: Semantic vector search for finding similar archives
    2. read_archives_data: Read-only metadata filtering and browsing (no write operations)
    """
    
    def __init__(self):
        logger.info("Initializing ArchiveSearchAgentV2 with middleware (LangChain 1.0)")
        
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
        self.memory = MemorySaver()
        
        # Create agent with search refinement middleware
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=SEARCH_AGENT_PROMPT,
            middleware=[search_refinement_middleware],  # Automatic retry logic
            checkpointer=self.memory,
        )
        logger.info("ArchiveSearchAgentV2 initialized with SearchRefinementMiddleware")
    
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
                    # Pure text response
                    return last_msg.content
        
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
