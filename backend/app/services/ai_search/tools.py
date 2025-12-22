"""Tools for AI search agent."""

import logging
from typing import List, Dict, Any, Optional
from langchain.tools import tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.core.supabase import get_supabase_client
from app.core.config import settings

# Configure logger
logger = logging.getLogger(__name__)


def normalize_public_url(url_response):
    """
    Normalize Supabase public URL response to a string.
    Handles both string URLs and dictionary responses.
    """
    if isinstance(url_response, str):
        return url_response
    elif isinstance(url_response, dict):
        # Supabase Python client may return {'publicUrl': '...'}
        return url_response.get('publicUrl') or url_response.get('publicurl') or url_response.get('url')
    return None


def get_embeddings_model():
    """Get Google's text embedding model."""
    logger.info("Initializing Google text-embedding-004 model")
    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=settings.GOOGLE_GENAI_API_KEY
    )


@tool(response_format="content_and_artifact")
def search_archives_db(
    query: str, 
    match_threshold: float = 0.7, 
    match_count: int = 10
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Search the archives database using vector similarity search.
    
    This tool performs semantic vector search to find heritage archives that match
    the provided query. It uses Google's text-embedding-004 model to generate 
    embeddings and searches against the Supabase vector database.
    
    The search focuses on finding the most relevant heritage materials based on
    semantic similarity, not exact keyword matching.
    
    Examples:
    - query="traditional Malaysian batik textiles" → Finds batik-related archives
    - query="wayang kulit shadow puppet performances" → Finds wayang kulit archives
    - query="Georgetown heritage architecture photographs" → Finds architectural photos
    
    Args:
        query: A concise, focused search query describing what heritage materials to find.
               Should capture the core search intent with relevant keywords and context.
        match_threshold: Minimum similarity score (0.0-1.0) to include results. 
                        Lower = more permissive. Default: 0.3
        match_count: Maximum number of results to return (1-20). Default: 10
        
    Returns:
        A tuple of (formatted_string, raw_documents) where:
        - formatted_string: A human-readable summary of found archives
        - raw_documents: The archive records with full details including similarity scores
    """
    logger.info(f"Starting archive search with query: '{query}'")
    
    # Get embedding model
    logger.debug("Getting embeddings model")
    embeddings = get_embeddings_model()
    
    # Get Supabase client
    logger.debug("Connecting to Supabase")
    supabase = get_supabase_client()
    
    # Validate and clamp parameters
    match_threshold = max(0.0, min(1.0, match_threshold))
    match_count = max(1, min(20, int(match_count)))
    
    try:
        # Generate embedding for the query
        logger.debug("Generating embedding for search query")
        query_embedding = embeddings.embed_query(query)
        logger.debug(f"Generated embedding with {len(query_embedding)} dimensions")
        
        # Perform vector similarity search
        logger.debug("Executing vector similarity search in database")
        result = supabase.rpc(
            'match_archives',
            {
                'query_embedding': query_embedding,
                'match_threshold': match_threshold,
                'match_count': match_count
            }
        ).execute()
        
        archives = result.data if result.data else []
        logger.info(f"Query '{query}' returned {len(archives)} result(s)")
        
        # Process each archive
        for archive in archives:
            # Remove embedding from the archive before returning
            # The agent doesn't need to see large embedding arrays
            if 'embedding' in archive:
                del archive['embedding']
            
            # Convert storage_paths to file_uris with full public URLs
            if 'storage_paths' in archive and archive['storage_paths']:
                file_uris = []
                for storage_path in archive['storage_paths']:
                    try:
                        public_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
                        public_url = normalize_public_url(public_url_response)
                        if public_url:
                            file_uris.append(public_url)
                    except Exception as e:
                        logger.warning(f"Error generating public URL for {storage_path}: {e}")
                
                # Set file_uris with full URLs
                archive['file_uris'] = file_uris
            else:
                archive['file_uris'] = []
        
        # Format the results for the agent
        if not archives:
            logger.warning(f"No matching archives found for query: '{query}'")
            return f"No matching archives found for the search query.", []
        
        # Create a formatted string for the agent to read
        logger.debug("Formatting search results for agent")
        formatted_results = []
        for i, archive in enumerate(archives, 1):
            archive_id = archive.get('id')
            archive_title = archive.get('title', 'Untitled')
            similarity = archive.get('similarity', 0)
            
            # Format dates if present
            dates_str = "None"
            if archive.get('dates'):
                dates_str = ', '.join([str(d) for d in archive.get('dates', [])])
            
            formatted_results.append(
                f"\n{i}. {archive_title}\n"
                f"   ID: {archive_id}\n"
                f"   Summary: {archive.get('summary', 'No summary available')[:200]}...\n"
                f"   Tags: {', '.join(archive.get('tags', []) or [])}\n"
                f"   Media Types: {', '.join(archive.get('media_types', []))}\n"
                f"   Dates: {dates_str}\n"
                f"   Number of Files: {len(archive.get('storage_paths', []) or [])}\n"
                f"   Similarity Score: {similarity:.2f}"
            )
        
        formatted_string = (
            f"Found {len(archives)} archive(s) matching the query:\n"
            + "\n".join(formatted_results)
        )
        
        logger.info(f"Successfully completed archive search: {len(archives)} archives found")
        return formatted_string, archives
        
    except Exception as e:
        logger.error(f"Search failed for query '{query}': {str(e)}")
        return f"Search failed: {str(e)}", []


@tool(response_format="content_and_artifact")
def read_archives_data(
    filter_by: Optional[str] = None,
    filter_value: Optional[str] = None,
    limit: int = 20,
    order_by: str = "created_at",
    order_desc: bool = True
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Read archive records from the Supabase database with flexible filtering.
    This is a READ-ONLY tool - no write, update, or delete operations are allowed.
    
    Use this tool when you need to:
    - Browse existing archives by specific criteria
    - Check archive metadata (title, tags, dates, media types)
    - Verify what archives exist in the database
    - Get detailed information about archives
    
    Available filters:
    - "tag": Filter archives containing a specific tag (e.g., "batik", "heritage")
    - "media_type": Filter by media type ("image", "video", "audio", "document")
    - "title": Search archives with title containing the filter value
    - "date_after": Filter archives created after a specific date (ISO format: YYYY-MM-DD)
    - "date_before": Filter archives created before a specific date (ISO format: YYYY-MM-DD)
    - None: Return all archives (default)
    
    Examples:
    - read_archives_data(filter_by="tag", filter_value="batik", limit=10)
      → Returns up to 10 archives tagged with "batik"
    - read_archives_data(filter_by="media_type", filter_value="video", limit=5)
      → Returns up to 5 video archives
    - read_archives_data(filter_by="title", filter_value="Georgetown")
      → Returns archives with "Georgetown" in the title
    - read_archives_data(limit=15, order_by="updated_at")
      → Returns 15 most recently updated archives
    
    Args:
        filter_by: Optional filter field ("tag", "media_type", "title", "date_after", "date_before")
        filter_value: Value to filter by (required if filter_by is specified)
        limit: Maximum number of records to return (1-50, default: 20)
        order_by: Field to sort by ("created_at", "updated_at", "title", default: "created_at")
        order_desc: Sort in descending order (default: True for newest first)
        
    Returns:
        A tuple of (formatted_string, raw_records) where:
        - formatted_string: Human-readable summary of found archives
        - raw_records: List of archive records with full metadata
    """
    logger.info(f"Reading archives data with filter: {filter_by}={filter_value}, limit={limit}")
    
    # Get Supabase client
    supabase = get_supabase_client()
    
    # Validate and clamp parameters
    limit = max(1, min(50, int(limit)))
    
    # Valid order_by fields
    valid_order_fields = ["created_at", "updated_at", "title"]
    if order_by not in valid_order_fields:
        order_by = "created_at"
    
    try:
        # Build the query - always select all fields except embedding (too large)
        query = supabase.table("archives").select(
            "id, title, description, media_types, tags, dates, "
            "created_at, updated_at, storage_paths"
        )
        
        # Apply filters if specified
        if filter_by and filter_value:
            if filter_by == "tag":
                # Filter arrays that contain the tag
                query = query.contains("tags", [filter_value])
            elif filter_by == "media_type":
                # Filter arrays that contain the media type
                query = query.contains("media_types", [filter_value])
            elif filter_by == "title":
                # Case-insensitive title search
                query = query.ilike("title", f"%{filter_value}%")
            elif filter_by == "date_after":
                # Filter archives created after specified date
                query = query.gte("created_at", filter_value)
            elif filter_by == "date_before":
                # Filter archives created before specified date
                query = query.lte("created_at", filter_value)
            else:
                logger.warning(f"Unknown filter type: {filter_by}")
        
        # Apply ordering
        query = query.order(order_by, desc=order_desc)
        
        # Apply limit
        query = query.limit(limit)
        
        # Execute query
        logger.debug(f"Executing read-only query on archives table")
        result = query.execute()
        
        archives = result.data if result.data else []
        logger.info(f"Retrieved {len(archives)} archive record(s)")
        
        # Process each archive
        for archive in archives:
            # Generate public URLs for storage paths
            if 'storage_paths' in archive and archive['storage_paths']:
                file_uris = []
                for storage_path in archive['storage_paths']:
                    try:
                        public_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
                        public_url = normalize_public_url(public_url_response)
                        if public_url:
                            file_uris.append(public_url)
                    except Exception as e:
                        logger.warning(f"Error generating public URL for {storage_path}: {e}")
                
                archive['file_uris'] = file_uris
            else:
                archive['file_uris'] = []
        
        # Format the results
        if not archives:
            filter_desc = f" matching filter '{filter_by}={filter_value}'" if filter_by else ""
            return f"No archives found{filter_desc}.", []
        
        # Create formatted string for the agent
        formatted_results = []
        for i, archive in enumerate(archives, 1):
            archive_id = archive.get('id')
            archive_title = archive.get('title', 'Untitled')
            created_at = archive.get('created_at', 'Unknown')
            
            # Format dates if present
            dates_str = "None"
            if archive.get('dates'):
                dates_str = ', '.join([str(d) for d in archive.get('dates', [])])
            
            formatted_results.append(
                f"\n{i}. {archive_title}\n"
                f"   ID: {archive_id}\n"
                f"   Description: {archive.get('description', 'No description')[:150]}...\n"
                f"   Tags: {', '.join(archive.get('tags', []) or [])}\n"
                f"   Media Types: {', '.join(archive.get('media_types', []))}\n"
                f"   Dates: {dates_str}\n"
                f"   Files: {len(archive.get('storage_paths', []) or [])}\n"
                f"   Created: {created_at}"
            )
        
        filter_desc = f" (filtered by {filter_by}={filter_value})" if filter_by else ""
        formatted_string = (
            f"Found {len(archives)} archive(s){filter_desc}:\n"
            + "\n".join(formatted_results)
        )
        
        logger.info(f"Successfully retrieved {len(archives)} archives")
        return formatted_string, archives
        
    except Exception as e:
        logger.error(f"Failed to read archives data: {str(e)}")
        return f"Failed to read archives: {str(e)}", []
