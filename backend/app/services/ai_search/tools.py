"""Tools for AI search agent."""

import logging
from typing import List, Dict, Any
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
    queries: List[str], 
    match_threshold: float = 0.3, 
    match_count: int = 5
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Search the archives database using vector similarity search with multiple queries.
    
    This tool performs vector search for multiple diverse query variations and combines
    the results, deduplicating by archive ID to provide comprehensive search coverage.
    
    IMPORTANT: To maximize search recall, you should ALWAYS generate 3-5 diverse query variations
    that capture different aspects of the user's intent. For example:
    - Original keywords
    - Synonyms and related terms  
    - More specific variations (e.g., "batik sarong" from "batik")
    - Broader contextual variations (e.g., "traditional Malaysian textiles" from "batik")
    - Cultural context (e.g., "heritage fabric patterns")
    
    Examples:
    - For "batik": ["batik", "batik fabric", "traditional Malaysian batik textiles", 
                    "batik sarong patterns", "hand-dyed batik heritage materials"]
    - For "crafts": ["traditional crafts", "heritage handicrafts", "cultural artisan work",
                     "Malaysian craftsmanship", "historical craft techniques"]
    
    Args:
        queries: A list of 3-5 diverse query variations to search for. Each query will be embedded and searched separately.
        match_threshold: Minimum similarity score (0.0-1.0) to include results. Lower = more permissive. Default: 0.3
        match_count: Maximum number of results to return PER QUERY (1-20). Default: 5
        
    Returns:
        A tuple of (formatted_string, raw_documents) where:
        - formatted_string: A human-readable summary of found archives across all queries
        - raw_documents: The deduplicated archive records with full details
    """
    # Ensure queries is a list
    if not isinstance(queries, list):
        query_list = [str(queries)]
        logger.warning(f"Queries should be a list, converting: {queries}")
    else:
        query_list = queries
    
    logger.info(f"Starting archive search with {len(query_list)} diverse queries: {query_list}")
    
    # Get embedding model once for all queries
    logger.debug("Getting embeddings model")
    embeddings = get_embeddings_model()
    
    # Get Supabase client
    logger.debug("Connecting to Supabase")
    supabase = get_supabase_client()
    
    # Validate and clamp parameters
    match_threshold = max(0.0, min(1.0, match_threshold))
    match_count = max(1, min(20, int(match_count)))
    
    # Collect all archives across queries, deduplicating by ID
    all_archives = {}  # Dict[str, Dict] - keyed by archive ID
    query_results = {}  # Track which queries found which archives
    
    for idx, query in enumerate(query_list, 1):
        try:
            logger.debug(f"Processing query {idx}/{len(query_list)}: '{query}'")
            
            # Generate embedding for this query
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
            
            # Track results for this query
            query_results[query] = []
            
            # Add archives to global collection (deduplicating by ID)
            for archive in archives:
                archive_id = archive.get('id')
                if archive_id:
                    # Remove embedding from the archive before storing
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
                    
                    query_results[query].append(archive_id)
                    
                    # Keep the version with highest similarity score if duplicate
                    if archive_id in all_archives:
                        existing_similarity = all_archives[archive_id].get('similarity', 0)
                        new_similarity = archive.get('similarity', 0)
                        if new_similarity > existing_similarity:
                            all_archives[archive_id] = archive
                            logger.debug(f"  Updated archive '{archive.get('title')}' with higher similarity: {new_similarity:.2f}")
                    else:
                        all_archives[archive_id] = archive
                        logger.debug(f"  Found new archive: {archive.get('title')} (ID: {archive_id}, similarity: {archive.get('similarity', 0):.2f})")
                        
        except Exception as e:
            logger.warning(f"Query '{query}' failed: {str(e)}")
            query_results[query] = []
            continue
    
    # Convert to list and sort by similarity (highest first)
    archives_list = sorted(
        all_archives.values(), 
        key=lambda x: x.get('similarity', 0), 
        reverse=True
    )
    
    # Format the results for the agent
    if not archives_list:
        logger.warning(f"No matching archives found across {len(query_list)} queries")
        return f"No matching archives found across {len(query_list)} search queries.", []
    
    # Create a formatted string for the agent to read
    logger.debug("Formatting combined search results for agent")
    formatted_results = []
    for i, archive in enumerate(archives_list, 1):
        archive_id = archive.get('id')
        archive_title = archive.get('title', 'Untitled')
        similarity = archive.get('similarity', 0)
        
        # Format dates if present
        dates_str = "None"
        if archive.get('dates'):
            dates_str = ', '.join([str(d) for d in archive.get('dates', [])])
        
        # Determine which queries found this archive
        found_by_queries = [q for q, ids in query_results.items() if archive_id in ids]
        
        formatted_results.append(
            f"\n{i}. {archive_title}\n"
            f"   ID: {archive_id}\n"
            f"   Summary: {archive.get('summary', 'No summary available')[:200]}...\n"
            f"   Tags: {', '.join(archive.get('tags', []) or [])}\n"
            f"   Media Types: {', '.join(archive.get('media_types', []))}\n"
            f"   Dates: {dates_str}\n"
            f"   Number of Files: {len(archive.get('genai_file_ids', []) or [])}\n"
            f"   Similarity Score: {similarity:.2f}\n"
            f"   Matched Queries: {len(found_by_queries)}/{len(query_list)}"
        )
    
    formatted_string = (
        f"Found {len(archives_list)} unique archive(s) across {len(query_list)} search queries:\n"
        f"Queries used: {query_list}\n"
        + "\n".join(formatted_results)
    )
    
    logger.info(f"Successfully completed multi-query archive search: {len(archives_list)} unique archives found")
    return formatted_string, archives_list
