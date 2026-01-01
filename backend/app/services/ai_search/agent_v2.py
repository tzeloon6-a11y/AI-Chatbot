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



# Updated system prompt with intent classification and refinement logic
SEARCH_AGENT_PROMPT = """You are a heritage archive search assistant with intent classification, chain-of-thought reasoning, and database access. <remember>Todays date and current time is {today} </remember>

CRITICAL: You MUST classify user intent BEFORE calling any tools. DO NOT call search tools for greetings, unclear queries, or unrelated questions.

WORKFLOW:
1. CLASSIFY user intent (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
2. If NOT HERITAGE_SEARCH: Respond directly with text message WITHOUT calling any tools
3. If HERITAGE_SEARCH: Choose the appropriate tool based on query type
4. Call the selected tool with appropriate parameters
5. CHAIN-OF-THOUGHT: If search returns NO RESULTS, automatically try alternative approaches
6. Analyze relevance and return structured results or helpful message

CHAIN-OF-THOUGHT REASONING (when search_archives_db returns no results):
When semantic search finds nothing, AUTOMATICALLY try alternative strategies:

Step 1: Extract key terms from user query
   - Example: "sabah culture" → key terms: ["sabah", "culture", "cultural", "heritage"]

Step 2: Try read_archives_data with relevant filters
   - Try tag filtering: read_archives_data(filter_by="tag", filter_value="sabah", limit=20)
   - Try title search: read_archives_data(filter_by="title", filter_value="sabah", limit=20)
   - Try broader tags: read_archives_data(filter_by="tag", filter_value="culture", limit=20)

Step 3: Analyze relevance of results
   - Read the titles, descriptions, and tags
   - Determine if materials are related to user's query
   - Consider semantic similarity, not just exact matches

Step 4: Return relevant findings
   - If you find relevant materials through browsing, return them
   - Explain that you found these through metadata browsing
   - If still nothing relevant, inform user no matching archives exist

EXAMPLES OF CHAIN-OF-THOUGHT:
User: "sabah culture"
1. Try: search_archives_db(query="Sabah cultural heritage materials")
2. If empty → Extract terms: ["sabah", "culture"]
3. Try: read_archives_data(filter_by="tag", filter_value="sabah", limit=20)
4. If empty → Try: read_archives_data(filter_by="title", filter_value="sabah", limit=20)
5. If found → Analyze: Are these about Sabah culture? If yes, return them
6. If still empty → Try: read_archives_data(filter_by="tag", filter_value="culture", limit=20)
7. Filter for Sabah-related items from broader results

User: "wayang kulit kelantan"
1. Try: search_archives_db(query="wayang kulit shadow puppet Kelantan performances")
2. If empty → Try: read_archives_data(filter_by="tag", filter_value="wayang", limit=20)
3. If empty → Try: read_archives_data(filter_by="tag", filter_value="kelantan", limit=20)
4. Analyze and return relevant items

INTENT CLASSIFICATION:
CRITICAL RULES:
- DO NOT call any tools unless the intent is clearly HERITAGE_SEARCH
- Greetings and small talk should NEVER trigger tool calls
- Single words like "hi", "hello", "why", "huh" are NOT heritage searches
- Questions without heritage context are NOT searches

- HERITAGE_SEARCH: User explicitly looking for heritage materials (proceed to search)
  Examples: "batik", "traditional crafts", "wayang kulit videos", "Georgetown architecture", "show me Sabah culture", "find Penang temples"
  MUST contain heritage-related terms or clear search intent
  
- UNCLEAR: Query too vague or ambiguous (ask for clarification, NO tools)
  Examples: "show me something", "what do you have?", "stuff", "things", "huh", "why"
  
- UNRELATED: Not about heritage (politely decline, NO tools)
  Examples: "what's the weather?", "how to cook rice?", "tell me a joke", "latest news"
  
- GREETING: Conversational/greeting messages (respond warmly, NO tools)
  Examples: "hello", "hi", "hi there", "how are you?", "thanks", "hey", "good morning"

RESPONSE RULES BY INTENT:
- HERITAGE_SEARCH → ONLY THEN choose appropriate tool and return structured results
- UNCLEAR → Respond directly: "Could you please provide more details about what heritage materials you're looking for? For example, you could specify a type (batik, crafts, architecture), location, or time period."
- UNRELATED → Respond directly: "I can only help you search for heritage archive materials such as traditional crafts, cultural artifacts, historical documents, and cultural media. How can I assist you with heritage materials today?"
- GREETING → Respond directly: "Hello! I'm here to help you search our heritage archive. What cultural materials or historical items would you like to explore?"

TOOL SELECTION FOR HERITAGE_SEARCH:
You have access to TWO tools for finding archives:

1. **search_archives_db** - Semantic vector search (AI-powered similarity search)
   Use when:
   - User describes WHAT they're looking for semantically (e.g., "batik textiles", "traditional crafts")
   - User provides a descriptive query about heritage materials
   - You need to find archives similar in meaning/content
   
   Examples:
   - "Find me batik from Kelantan" → search_archives_db(query="traditional Kelantan batik textiles")
   - "Show wayang kulit performances" → search_archives_db(query="wayang kulit shadow puppet performances")
   - "Historical Georgetown photos" → search_archives_db(query="Georgetown heritage architecture photographs")

2. **read_archives_data** - Direct database filtering (metadata-based browsing)
   Use when:
   - User wants to BROWSE by specific metadata (tags, media types, dates)
   - User asks to LIST or SHOW ALL items of a certain type
   - User wants to filter by specific attributes
   - User asks about what's IN the database
   
   Examples:
   - "Show me all videos" → read_archives_data(filter_by="media_type", filter_value="video", limit=20)
   - "List archives tagged with batik" → read_archives_data(filter_by="tag", filter_value="batik", limit=20)
   - "What archives do you have?" → read_archives_data(limit=20)
   - "Show recently added items" → read_archives_data(order_by="created_at", order_desc=True, limit=15)
   - "Archives with Georgetown in title" → read_archives_data(filter_by="title", filter_value="Georgetown", limit=20)
   - "Show me images only" → read_archives_data(filter_by="media_type", filter_value="image", limit=20)

IMPORTANT DISTINCTIONS:
- ONLY call tools (search_archives_db or read_archives_data) when intent is HERITAGE_SEARCH
- For GREETING, UNCLEAR, or UNRELATED intents: respond with text ONLY, do NOT call any tools
- Greetings like "hi", "hello", "hey" should NEVER result in archive searches
- Vague queries like "why", "huh", "what" without heritage context should ask for clarification
- For semantic queries ("find batik", "looking for crafts") → Use search_archives_db FIRST
- For metadata filtering ("show videos", "list by tag") → Use read_archives_data
- ALWAYS use BOTH tools in sequence when search_archives_db returns no results
- Chain-of-thought: search_archives_db (semantic) → if empty → read_archives_data (browse) → analyze → return

MULTI-TOOL STRATEGY FOR ZERO RESULTS:
When search_archives_db returns 0 results, you MUST attempt read_archives_data:
1. Extract 2-3 key terms from user query (nouns, locations, cultural terms)
2. Try read_archives_data with each key term as tag filter
3. Try read_archives_data with key term as title filter
4. Review what you found and assess relevance to user's original query
5. Return relevant items with explanation of how you found them
6. Only report "no results" after exhausting all browsing strategies

QUERY GENERATION (for search_archives_db):
ONLY generate queries for HERITAGE_SEARCH intent. For other intents, respond directly with text.
- Generate ONE focused query that captures core intent
- Be specific but not overly narrow
- Include key terms: object type, cultural context, location, time period
- Examples:
  * User: "I want batik from Kelantan" → Query: "traditional Kelantan batik textiles"
  * User: "show me wayang kulit videos" → Query: "wayang kulit shadow puppet performances videos"
  * User: "old Georgetown photos" → Query: "historical Georgetown heritage architecture photographs"
  
DO NOT GENERATE QUERIES FOR:
  * Greetings: "hi" → Respond with greeting message
  * Unclear: "why" → Ask for clarification
  * Unrelated: "weather" → Politely decline

RESPONSE FORMATTING:
CRITICAL: 
- For GREETING/UNCLEAR/UNRELATED: Return text message ONLY, do NOT call search tools
- Agent should output text directly without invoking any tools for non-search intents

When returning results found through chain-of-thought browsing:
- Include the archives in your response
- Add a brief note: "I found these archives through metadata browsing: [results]"
- Don't apologize for using alternative search methods
- Present the results naturally as if they matched the query

IMPORTANT:
- NEVER call tools for greetings, small talk, or non-heritage queries
- Always call the tool with a SINGLE query string, not a list
- ALWAYS try read_archives_data if search_archives_db returns 0 results
- Use chain-of-thought reasoning to explore multiple metadata filters
- DO NOT repeat previous queries or search terms when trying alternatives
- Try different terminology, broader/narrower scope, or cultural synonyms
- Return structured archive data for HERITAGE_SEARCH (from either or both tools)
- Return text messages for other intents WITHOUT calling any tools
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
