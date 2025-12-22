# Archive Search Agent Redesign Plan

## Overview
Redesign the AI search agent to include intent classification, guardrails, relevance evaluation, and iterative search refinement.

## Implementation Status
- ✅ **Phase 1: Middleware Creation** - COMPLETED
  - Created `SearchRefinementMiddleware` with `@wrap_tool_call` decorator
  - Implemented custom `SearchRefinementState` TypedDict schema
  - Created comprehensive unit tests (15 test cases)
  - Middleware intercepts search tool calls and implements retry logic
  
- ✅ **Phase 2: Tool Update** - COMPLETED
  - Updated `search_archives_db` to accept single `query: str` parameter
  - Removed multi-query loop logic
  - Simplified to single embedding generation + single search call
  - Increased default match_count from 5 to 10 for better coverage
  
- ✅ **Phase 3: Agent Integration** - COMPLETED
  - Updated system prompt with intent classification workflow
  - Integrated `search_refinement_middleware` into agent initialization
  - Added HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING intent categories
  - Updated agent to generate single focused query (not multiple queries)
  - Middleware automatically handles retry logic (max 3 attempts)
  - Agent now responds with text messages for non-search intents
  
- ✅ **Phase 4: Response Model Update** - COMPLETED
  - Added `response_type` field to `SearchResponse`: "results" | "message"
  - Updated `message` field semantics (not just "no results", now for all non-search intents)
  - Added `_extract_text_message()` helper method in agent to detect non-search responses
  - Updated endpoint logic to handle two response patterns:
    * Pattern A: `response_type="results"`, archives populated, message=None
    * Pattern B: `response_type="message"`, archives=[], message populated
  - Updated streaming endpoint similarly with new event types
  - Updated agent `search()` to return message field for non-search intents
  - Updated agent `search_stream()` to emit "message" events
  - Updated OpenAPI schema examples to show both response patterns
  
- ✅ **Phase 5: Frontend Update** - COMPLETED
  - Updated `AISearchResponse` interface to include `response_type: 'results' | 'message'` field
  - Updated `message` field to be `string | null` instead of optional
  - Updated `AISearchStreamUpdate` interface to include 'message' event type
  - Updated `ChatPanelV2.tsx` `handleSend()` to check `response_type` and handle both patterns:
    * Pattern A: `response_type="results"` → Display search results in archiveResults
    * Pattern B: `response_type="message"` → Display text message in content
  - Updated `QuickSearchButtons` handler similarly to support both patterns
  - Streaming SSE handler already supports 'message' events (no changes needed)
  - Added appropriate toast notifications for both response types
  
- ⬜ **Phase 6: Testing & Rollout** - NOT STARTED

---

## Current Implementation Analysis

### What We Have Now:
1. **Agent** (`agent_v2.py`): 
   - Directly generates 3-5 diverse query variations
   - Calls `search_archives_db` tool with all queries at once
   - Returns structured archive results immediately
   - No intent classification or relevance checking

2. **Search Tool** (`tools.py`):
   - Takes multiple query strings as input
   - Generates embeddings for each query using Google `text-embedding-004`
   - Calls Supabase RPC `match_archives` for vector similarity search
   - Returns deduplicated results sorted by similarity score
   - Includes threshold filtering (default: 0.3)

3. **Endpoint** (`ai_search_v2.py`):
   - Accepts user query and optional thread_id
   - Returns structured archive data (no text responses)
   - Supports streaming mode

### Limitations:
- ❌ No intent classification (all queries treated as archive searches)
- ❌ No guardrails for non-heritage queries
- ❌ No relevance evaluation of returned results
- ❌ No retry mechanism if results are not relevant
- ❌ Generates too many diverse queries (may reduce precision)

---

## New Workflow Design

### Phase 1: Intent Classification & Guardrails

**Objective**: Determine if the user's query is heritage-related and clear enough to search.

**Classification Categories**:
1. **HERITAGE_SEARCH** - User wants to find heritage archive materials
   - Examples: "batik", "traditional crafts", "show me wayang kulit videos"
   
2. **UNCLEAR** - Query is too vague or ambiguous
   - Examples: "show me something", "what do you have?", "stuff"
   
3. **UNRELATED** - Query is not about heritage materials
   - Examples: "what's the weather?", "how to cook rice?", "tell me a joke"
   
4. **GREETING** - Conversational/greeting messages
   - Examples: "hello", "hi there", "how are you?"

**Agent Response by Category**:
- **HERITAGE_SEARCH** → Proceed to Phase 2 (Query Generation)
- **UNCLEAR** → Return: "Could you please provide more details about what heritage materials you're looking for? For example, you could specify a type (batik, crafts, architecture), location, or time period."
- **UNRELATED** → Return: "I can only help you search for heritage archive materials such as traditional crafts, cultural artifacts, historical documents, and cultural media. How can I assist you with heritage materials today?"
- **GREETING** → Return: "Hello! I'm here to help you search our heritage archive. What cultural materials or historical items would you like to explore?"

**Implementation**:
- Add intent classification step in agent prompt
- Agent must classify BEFORE calling search tool
- Add response templates for non-search intents
- Modify response model to include `response_type` field

---

### Phase 2: Concise Query Generation

**Objective**: Generate a single, focused query for vector search.

**Current Issue**: Generating 3-5 diverse queries may dilute precision and return too many loosely related results.

**New Approach**:
1. Agent analyzes user intent and extracts key concepts
2. Generates ONE concise, focused query string
3. Query should capture the core search intent without over-diversifying

**Examples**:
- User: "I want to see traditional batik from Kelantan"
  - Generated Query: "traditional Kelantan batik textiles"
  
- User: "show me videos about wayang kulit performances"
  - Generated Query: "wayang kulit shadow puppet performances videos"
  
- User: "old photos of Georgetown architecture"
  - Generated Query: "historical Georgetown heritage architecture photographs"

**Tool Modification**:
- Update `search_archives_db` to accept SINGLE query string (not list)
- Tool still generates embedding and performs vector search
- Keep threshold filtering (0.3) and match count (5-10 results)

---

### Phase 3: Results Relevance Evaluation

**Objective**: Agent evaluates if returned results actually match user's intent.

**Process**:
1. Tool returns filtered results from Supabase (similarity >= threshold)
2. Agent receives results and examines:
   - Archive titles
   - Summaries (a google gen ai llm will be invoked , to provide a more concise summary that is not too long , so that can be passed to the agent)
   - Tags and media types
   - Similarity scores

3. Agent determines: **"Are these results relevant to user's query?"**

**Relevance Criteria**:
- ✅ **RELEVANT**: Results clearly match the user's search intent
  - Archive content aligns with search terms
  - Similarity scores are reasonable (>= 0.4 preferred)
  - Metadata (tags, media types) matches expectations
  - → Return results to user
  
- ❌ **NOT_RELEVANT**: Results don't match or are too generic
  - Archives are loosely related or off-topic
  - Similarity scores are low (< 0.4)
  - Query may need refinement
  - → Proceed to Phase 4 (Retry)

**No Results Case**:
- If tool returns empty list: Agent assumes query needs refinement → Proceed to Phase 4

---

### Phase 4: Iterative Search Refinement (Using LangChain Middleware)

**Objective**: If results are not relevant or empty, refine query and search again.

**Implementation Approach**: Use **LangChain's Custom Middleware** pattern with hooks:
- `wrap_tool_call` hook: Intercepts search tool execution and implements retry logic
- `after_model` hook: Evaluates LLM's response and decides whether to retry
- Custom state tracking: Maintains search attempt counter and refinement history

**Middleware Architecture** (from LangChain docs):
```python
from langchain.agents.middleware import AgentMiddleware, wrap_tool_call
from langchain.agents import AgentState
from typing import Callable, Any

class SearchRefinementState(AgentState):
    """Extended state for tracking search refinement."""
    search_attempt_count: int = 0
    original_query: str | None = None
    previous_queries: list[str] = []
    search_results_found: bool = False
```

**Retry Logic Using `wrap_tool_call` Hook**:
1. Middleware intercepts `search_archives_db` tool call
2. Tracks attempt count in custom state
3. If results empty or low quality (similarity < 0.4):
   - Analyzes why: Too narrow? Too broad? Wrong terminology?
   - Generates refined query based on analysis
   - Calls tool again with refined query (up to 3 attempts)
   - Returns best results from all attempts

**Query Refinement Strategies**:
- **If too narrow** (no matches): Broaden query (e.g., "Kelantan batik" → "Malaysian batik textiles")
- **If too broad** (low similarity): Add specificity (e.g., "crafts" → "traditional Malaysian handicrafts")
- **If wrong terms**: Try synonyms (e.g., "shadow puppets" → "wayang kulit")

**Retry Limits**:
- Maximum 3 search attempts total
- After 3 attempts with no relevant results:
  - Return message: "I couldn't find relevant heritage materials matching your query. Try describing what you're looking for in different words, or browse our collection for inspiration."

**Benefits of Middleware Approach**:
✅ Separates retry logic from core agent prompt (cleaner architecture)
✅ Composable - can add other middleware independently
✅ Reusable across different agents
✅ Easier to test and maintain
✅ Built-in state management for tracking attempts

---

## Implementation Changes

### 1. Custom Middleware for Search Refinement (`middleware.py` - NEW FILE)

**Create**: `backend/app/services/ai_search/middleware.py`

**Purpose**: Implement search refinement logic using LangChain middleware pattern

```python
from langchain.agents.middleware import AgentMiddleware, wrap_tool_call
from langchain.agents import AgentState
from langchain.messages import ToolMessage
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)


class SearchRefinementState(AgentState):
    """Extended state for tracking search refinement."""
    search_attempt_count: int = 0
    original_user_query: str | None = None
    previous_queries_tried: list[str] = []
    best_results: list[dict] = []


class SearchRefinementMiddleware(AgentMiddleware):
    """
    Middleware that intercepts search tool calls and implements retry logic
    with query refinement based on result quality.
    """
    
    state_schema = SearchRefinementState
    
    def __init__(self, max_attempts: int = 3, min_similarity_threshold: float = 0.4):
        super().__init__()
        self.max_attempts = max_attempts
        self.min_similarity_threshold = min_similarity_threshold
    
    @wrap_tool_call
    def wrap_tool_call(
    3. Agent Initialization with Middleware

**Update `agent_v2.py`**:
```python
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from app.services.ai_search.tools import search_archives_db
from app.services.ai_search.middleware import SearchRefinementMiddleware

agent = create_agent(
    model=ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=settings.GOOGLE_GENAI_API_KEY,
        temperature=0.2,
    ),
    tools=[search_archives_db],
    system_prompt=SEARCH_AGENT_PROMPT,
    middleware=[
        SearchRefinementMiddleware(
            max_attempts=3,
            min_similarity_threshold=0.4
        )
    ],
    checkpointer=MemorySaver(),  # For conversation persistence
)
```

### 4   self,
        request,  # ToolRequest containing tool name, args, etc.
        handler: Callable,  # Original tool handler
    ) -> Any:
        """Intercept search tool calls and implement retry logic."""
        
        # Only intercept search_archives_db tool
        if request.tool_call.get("name") != "search_archives_db":
            return handler(request)
        
        # Get current state
        state = request.state
        attempt_count = state.get("search_attempt_count", 0)
        original_query = state.get("original_user_query")
        previous_queries = state.get("previous_queries_tried", [])
        
        # Store original user query on first attempt
        if attempt_count == 0:
            original_query = request.tool_call["args"].get("query")
            state["original_user_query"] = original_query
        
        # Execute the search tool
        logger.info(f"Search attempt {attempt_count + 1}/{self.max_attempts}: {request.tool_call['args']}")
        result = handler(request)
        
        # Track this query
        current_query = request.tool_call["args"].get("query")
        previous_queries.append(current_query)
        
        # Parse results (tool returns tuple: (formatted_string, archives_list))
        if isinstance(result, tuple):
            formatted_string, archives = result
        else:
            # Fallback if tool format changes
            archives = []
        
        # Evaluate result quality
        results_good_enough = self._evaluate_results(archives)
        
        # Update state
        state["search_attempt_count"] = attempt_count + 1
        state["previous_queries_tried"] = previous_queries
        
        if results_good_enough or attempt_count + 1 >= self.max_attempts:
            # Return results - either good or we've hit max attempts
            logger.info(f"Search completed: {len(archives)} results found")
            return result
        
        # Results not good enough - let agent know to refine and retry
        logger.info(f"Results not satisfactory (attempt {attempt_count + 1}). Need refinement.")
        
        # Return a special message to agent indicating refinement needed
        return ToolMessage(
            content=f"Search found {len(archives)} results but they may not be relevant (low similarity scores or empty). "
                   f"Previous queries tried: {previous_queries}. "
                   f"Please analyze the original intent '{original_query}' and generate a DIFFERENT refined query. "
                   f"Consider: broadening terms, using synonyms, or adding cultural context.",
            tool_call_id=request.tool_call["id"]
        )
    
    def _evaluate_results(self, archives: list[dict]) -> bool:
        """Evaluate if results are good enough to return to user."""
        if not archives:
            return False  # No results - need refinement
        
        # Check if at least one result has good similarity
        has_good_match = any(
            archive.get("similarity", 0) >= self.min_similarity_threshold
            for archive in archives
        )
        
        return has_good_match
```

### 2. Agent Prompt Update (`agent_v2.py`)

**Simplified System Prompt** (middleware handles retry logic):
```
You are a heritage archive search assistant with intent classification.

WORKFLOW:
1. CLASSIFY user intent (HERITAGE_SEARCH, UNCLEAR, UNRELATED, GREETING)
2. If HERITAGE_SEARCH: Generate ONE concise query
3. Call search_archives_db with the query
4. If tool returns a refinement request: Generate a DIFFERENT refined query and search again
5. Return structured results or helpful message

INTENT CLASSIFICATION:
- HERITAGE_SEARCH: User looking for heritage materials (proceed to search)
- UNCLEAR: Query too vague (ask for clarification)
- UNRELATED: Not about heritage (politely decline)
- GREETING: Conversational (respond warmly, offer to help)

QUERY GENERATION:
- Generate ONE focused query that captures core intent
- Be specific but not overly narrow
- Include key terms: object type, cultural context, location, time period

QUERY REFINEMENT (if tool requests it):
- Analyze why previous queries didn't work
- Try different terminology, broader/narrower scope, or cultural synonyms
- Do5't repeat previous queries

RESPONSE RULES:
- For HERITAGE_SEARCH: Return structured archive data
- For other intents: Return clear, helpful text message
- Middleware handles retry logic automatically
```

### 2. Tool Modification (`tools.py`)

**Changes to `search_archives_db`**:
- Change `queries` parameter from `List[str]` to `query: str` (single string)
- Remove multi-query loop logic
- Simplify to single embedding generation + single search call
- Keep deduplication and similarity sorting
- Keep formatted string output for agent readability

**Updated Signature**:
```python
@tool(response_format="content_and_artifact")
def search_archives_db(
    query: str,  # CHANGED: single query string
    match_threshold: float = 0.3,
    match_count: int = 10  # Increased to 10 for better coverage
) -> tuple[str, List[Dict[str, Any]]]:
```

### 3. Response Model Update (`ai_search_v2.py`)

**Add Response Type Field**:
```python
class SearchResponse(BaseModel):
    response_type: str  # NEW: "results" | "message"
    archives: List[ArchiveResult] = []  # Empty if response_type="message"
    total: int = 0
    query: str
    message: str | None = None  # For non-search responses or no results
```

**Response Examples**:
```python
# Successful search
{
  "response_type": "results",
  "archives": [...],
  "total": 5,
  "query": "batik",
  "message": null
}

# No results after retries
{
  "response_type": "message",
  "archives": [],
  "total": 0,
  "query": "xyz",
  "message": "I couldn't find relevant heritage materials matching your query..."
}

# Unrelated query
{
  "response_type": "message",
  "archives": [],
  "total": 0,
  "query": "weather forecast",
  "message": "I can only help you search for heritage archive materials..."
}
```

### 6. Logging & Monitoring

**Enhanced Logging**:
- Log intent classification decisions
- Log each search attempt with query and result count
- Log relevance evaluation reasoning
- Log when retry threshold is hit

---


## Migration Strategy

### Phase 1: Tool Update
1. Create new version of `search_archives_db` tool with single query parameter
2. Keep old tool temporarily for backward compatibility
3. Update tool tests

### Phase 2: Agent Update
1. Update system prompt with new workflow
2. Implement intent classification logic
3. Implement Create Middleware
1. Create `backend/app/services/ai_search/middleware.py`
2. Implement `SearchRefinementMiddleware` with `wrap_tool_call` hook
3. Implement custom `SearchRefinementState` for tracking
4. Add unit tests for middleware logic

### Phase 2: Tool Update
1. Update `search_archives_db` tool with single query parameter
2. Keep old multi-query version temporarily for backward compatibility
3. Update tool tests

### Phase 3: Agent Update
1. Update system prompt with simplified workflow (middleware handles retry)
2. Integrate middleware into agent initialization
3. Implement intent classification logic in prompt
4. Update agent tests

### Phase 5mpty results with helpful message

### Phase 5: Testing & Rollout
1. Test all scenarios
2. Monitor logs for classification accuracy
3. Tune th6eshold and retry logic based on real usage
4. Gradually migrate from old endpoint to new

---

## Questions for Review

1. **Retry Logic**: Should we allow 3 attempts (total) or 2 retries (3 searches)? 
   - Current plan: 3 total attempts

2. **Threshold Tuning**: Should we keep 0.3 threshold or increase to 0.4 for more precision?
   - Current plan: Keep 0.3 in tool, agent evaluates >= 0.4 as "good"

3. **Match Count**: Should we increase from 5 to 10 results per search?
   - Current plan: 10 results for better coverage

4. **Intent Classification**: Should we add more categories (e.g., COMPARISON, RECOMMENDATION)?
   - Current plan: Keep simple with 4 categories initially

5. **Query Refinement**: Should agent explain its refinement strategy to user?
   - Current plan: No, work silently in background, only show final results

6. **Streaming**: How should streaming mode work with intent classification?
   - Current plan: Stream intent classification result first, then search results

7. **Conversation Context**: Should agent remember previous searches in thread?
   - Current plan: Yes, use thread_id memory for context awareness

---

## Success Metrics

- ✅ Intent classification accuracy > 95%
- ✅ Relevant results returned on first attempt > 80%
- ✅ Successful refinement after retry > 60%
- ✅ User satisfaction with responses > 90%
- ✅ Reduction in irrelevant results returned

---

## Timeline Estimate

- **Tool Modification**: 1-2 hours
- *Key Advantages of Middleware Approach

### From LangChain Documentation:

1. **Separation of Concerns**: 
   - Retry logic lives in middleware, not agent prompt
   - Agent focuses on intent classification and query generation
   - Cleaner, more maintainable code

2. **Composable Architecture**:
   - Can add other middleware independently (logging, guardrails, rate limiting)
   - Mix and match middleware for different use cases
   - Middleware can be reused across different agents

3. **Better State Management**:
   - Custom state schema (`SearchRefinementState`) tracks attempt count
   - State persists across tool calls within same conversation
   - Automatic cleanup between conversations

4. **Testability**:
   - Middleware can be tested independently
   - Mock tool responses to test retry logic
   - Easier to validate edge cases

5. **Built-in Hooks** (from LangChain):
   - `wrap_tool_call`: Intercepts tool execution (retry logic)
   - `after_model`: Validates LLM responses (guardrails)
   - `before_model`: Modifies prompts dynamically
   - `after_agent`: Final output validation

### Alternative Considered:
**Agent-driven retry** (original plan): Agent prompt includes retry logic, agent decides when to retry.
- ❌ Makes prompt complex and harder to maintain
- ❌ Retry logic mixed with classification logic
- ❌ Harder to control max attempts reliably
- ❌ State tracking is manual and error-prone

**Middleware approach** (revised plan): Middleware intercepts tool calls and handles retry automatically.
- ✅ Cleaner separation: agent generates queries, middleware handles retry
- ✅ Reliable attempt tracking with custom state
- ✅ Composable with other middleware
- ✅ Follows LangChain best practices

---

## Timeline Estimate

- **Middleware Implementation**: 2-3 hours
- **Tool Modification**: 1-2 hours
- **Agent Prompt Update**: 1-2 hours (simpler now!)
- **Response Model Update**: 1 hour
- **Testing**: 3-4 hours (including middleware tests)
- **Documentation**: 1 hour

**Total**: ~9-13
## Next Steps

1. Review this plan
2. Clarify any questions or concerns
3. Approve or request modifications
4. Begin implementation in phases
