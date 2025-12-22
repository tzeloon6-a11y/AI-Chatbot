from datetime import datetime
from typing import List
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends

from app.schemas.archive import ArchiveResponse, ArchiveUpdate, MediaType
from app.services.archive_service import ArchiveService
from app.core.supabase import get_supabase_client
from app.core.config import settings


router = APIRouter()


def get_archive_service() -> ArchiveService:
    """Dependency to get ArchiveService instance."""
    return ArchiveService()


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


@router.get("/archives", response_model=List[ArchiveResponse])
async def get_archives():
    """
    Retrieve all archives from the database.
    
    Returns a list of all archived items with their metadata, summaries, and embeddings.
    File URIs are converted to public URLs for storage paths.
    """
    
    supabase = get_supabase_client()
    
    # Query all archives from Supabase, ordered by creation date (newest first)
    response = supabase.table("archives").select("*").order("created_at", desc=True).execute()
    
    archives = []
    for record in response.data:
        # Remove summary and embedding from response - these are internal only
        record.pop("summary", None)
        record.pop("embedding", None)
        
        # Generate public URLs for storage paths
        file_uris = []
        if "storage_paths" in record and record["storage_paths"]:
            for storage_path in record["storage_paths"]:
                try:
                    # Get public URL for the storage path
                    public_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
                    public_url = normalize_public_url(public_url_response)
                    if public_url:
                        file_uris.append(public_url)
                except Exception as e:
                    print(f"Error generating public URL for {storage_path}: {e}")
                    continue
        
        # Always set file_uris, even if empty
        # Frontend will use these for download links
        if file_uris:
            record["file_uris"] = file_uris
        else:
            # If no storage paths, use placeholder
            record["file_uris"] = []
        
        archives.append(record)
    
    return archives
        
    


@router.post("/archives/generate-metadata")
async def generate_metadata(
    files: List[UploadFile] = File(..., description="Files to analyze for metadata generation"),
    media_types: str = Form(..., description="Comma-separated list of media types (image,video,audio,document)"),
    archive_service: ArchiveService = Depends(get_archive_service)
):
    """
    Generate metadata suggestions (title, tags, description) from uploaded files.
    This is called before the actual archive creation to provide AI-generated suggestions.
    
    Returns:
        Dictionary with suggested title, tags, and description
    """
    try:
        # Parse media types
        media_type_list = [MediaType(mt.strip().lower()) for mt in media_types.split(",") if mt.strip()]
        if not media_type_list:
            raise HTTPException(status_code=400, detail="At least one media type must be provided")
        
        # Validate files
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one file must be uploaded")
        
        # Convert media types to strings for service
        media_types_str = [mt.value for mt in media_type_list]
        
        # Upload files to GenAI
        uploaded_files, storage_paths, _ = await archive_service.upload_files_to_genai(files)
        
        # Generate metadata suggestions
        metadata = await archive_service.generate_metadata_suggestions(
            uploaded_files=uploaded_files,
            media_types=media_types_str
        )
        
        # Clean up uploaded files from GenAI and storage (since this is just for suggestions)
        # Delete from Supabase storage
        supabase = get_supabase_client()
        for storage_path in storage_paths:
            try:
                supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
            except Exception as e:
                print(f"Error cleaning up storage path {storage_path}: {e}")
        
        return metadata
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate metadata: {str(e)}"
        )


@router.post("/archives", response_model=ArchiveResponse, status_code=201)
async def create_archive(
    files: List[UploadFile] = File(..., description="Files to upload (images, videos, audio, documents)"),
    title: str = Form(..., description="Title of the archive"),
    media_types: str = Form(..., description="Comma-separated list of media types (image,video,audio,document)"),
    tags: str = Form(default="", description="Comma-separated list of tags"),
    description: str = Form(default="", description="Description of the archive content"),
    dates: str = Form(default="", description="Comma-separated ISO format dates"),
    archive_service: ArchiveService = Depends(get_archive_service)
):
    """
    Create a new archive by uploading files, analyzing content, and generating embeddings.
    
    Process:
    1. Upload files to Google GenAI
    2. Analyze content with comprehensive AI prompt
    3. Generate text embedding from summary
    4. Return archive with summary and embedding
    """
    try:
        # Parse media types
        media_type_list = [MediaType(mt.strip().lower()) for mt in media_types.split(",") if mt.strip()]
        if not media_type_list:
            raise HTTPException(status_code=400, detail="At least one media type must be provided")
        
        # Parse tags
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
        
        # Parse dates
        date_list = []
        if dates:
            for date_str in dates.split(","):
                date_str = date_str.strip()
                if date_str:
                    try:
                        date_list.append(datetime.fromisoformat(date_str))
                    except ValueError:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid date format: {date_str}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                        )
        
        # Validate files
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one file must be uploaded")
        
        # Convert media types to strings for service
        media_types_str = [mt.value for mt in media_type_list]
        
        # Process archive through service and persist to Supabase
        archive = await archive_service.process_archive(
            files=files,
            title=title,
            media_types=media_types_str,
            tags=tag_list,
            description=description,
            dates=date_list,
        )

        return archive
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create archive: {str(e)}"
        )


@router.delete("/archives/{archive_id}", status_code=204)
async def delete_archive(archive_id: str):
    """
    Delete an archive by ID.
    
    This will:
    1. Delete the archive record from the database
    2. Delete associated files from Supabase storage
    3. Delete files from Google GenAI (if any)
    """
    try:
        supabase = get_supabase_client()
        
        # First, get the archive to retrieve storage paths and GenAI file IDs
        response = supabase.table("archives").select("*").eq("id", archive_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail=f"Archive with ID {archive_id} not found")
        
        archive = response.data[0]
        
        # Delete files from Supabase storage if they exist
        if "storage_paths" in archive and archive["storage_paths"]:
            for storage_path in archive["storage_paths"]:
                try:
                    supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
                    print(f"Deleted file from storage: {storage_path}")
                except Exception as e:
                    print(f"Error deleting file from storage {storage_path}: {e}")
                    # Continue even if file deletion fails
        
        # Delete the archive record from the database
        delete_response = supabase.table("archives").delete().eq("id", archive_id).execute()
        
        if not delete_response.data:
            raise HTTPException(status_code=500, detail="Failed to delete archive from database")
        
        return None  # 204 No Content
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete archive: {str(e)}"
        )


@router.get("/archives/{archive_id}/download/{file_index}", status_code=200)
async def download_archive_file(archive_id: str, file_index: int):
    """
    Get a downloadable signed URL for a specific file in an archive.
    
    This returns a signed URL that forces the browser to download the file
    instead of displaying it. The URL is valid for 60 seconds.
    file_index: 0-based index of the file in the archive's storage_paths
    """
    try:
        supabase = get_supabase_client()
        
        # Get the archive
        response = supabase.table("archives").select("*").eq("id", archive_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail=f"Archive with ID {archive_id} not found")
        
        archive = response.data[0]
        
        # Get storage paths
        storage_paths = archive.get("storage_paths", [])
        
        if not storage_paths:
            raise HTTPException(status_code=404, detail="No files found for this archive")
        
        if file_index < 0 or file_index >= len(storage_paths):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file index. Archive has {len(storage_paths)} file(s)"
            )
        
        storage_path = storage_paths[file_index]
        
        # Generate signed URL with download parameter to force download
        try:
            # Create signed URL that expires in 60 seconds and forces download
            signed_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
                storage_path,
                60,  # expires in 60 seconds
                {"download": True}  # Force browser to download instead of display
            )
            
            # The response can be a dict with 'signedURL' key or a string
            if isinstance(signed_url_response, dict):
                signed_url = signed_url_response.get('signedURL') or signed_url_response.get('signedUrl')
            else:
                signed_url = signed_url_response
            
            if not signed_url:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create signed download URL"
                )
            
            # Extract filename from storage path
            filename = storage_path.split('/')[-1]
            
            return {
                "url": signed_url, 
                "storage_path": storage_path,
                "filename": filename,
                "expires_in": 60
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate download URL: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get download URL: {str(e)}"
        )


@router.put("/archives/{archive_id}", response_model=ArchiveResponse)
async def update_archive(
    archive_id: str,
    update_data: ArchiveUpdate,
    archive_service: ArchiveService = Depends(get_archive_service)
):
    """
    Update an existing archive item.
    
    When user edits their archive (title, description, tags, dates), 
    the AI summary is automatically regenerated to reflect the updated information.
    The summary remains hidden from the user but is updated in the database.
    
    Process:
    1. Retrieve existing archive from database
    2. Update user-editable fields
    3. Regenerate AI summary with updated metadata
    4. Generate new embedding from updated summary
    5. Update database with new summary and embedding
    """
    try:
        supabase = get_supabase_client()
        
        # Get existing archive
        response = supabase.table("archives").select("*").eq("id", archive_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail=f"Archive with ID {archive_id} not found")
        
        existing_archive = response.data[0]
        
        # Prepare update payload with user-editable fields
        update_payload = {}
        
        if update_data.title is not None:
            update_payload["title"] = update_data.title
        
        if update_data.description is not None:
            update_payload["description"] = update_data.description
        
        if update_data.tags is not None:
            update_payload["tags"] = update_data.tags
        
        if update_data.dates is not None:
            update_payload["dates"] = [dt.isoformat() for dt in update_data.dates]
        
        # Check if any fields were actually updated
        if not update_payload:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Get storage paths to fetch files from Supabase
        storage_paths = existing_archive.get("storage_paths", [])
        
        if not storage_paths:
            # If no storage paths, just update the metadata without regenerating summary
            update_response = supabase.table("archives").update(update_payload).eq("id", archive_id).execute()
            
            if not update_response.data:
                raise HTTPException(status_code=500, detail="Failed to update archive")
            
            updated_archive = update_response.data[0]
            
            # Remove summary and embedding from response
            updated_archive.pop("summary", None)
            updated_archive.pop("embedding", None)
            
            # Add file URIs
            file_uris = []
            updated_archive["file_uris"] = file_uris
            return updated_archive
        
        # Fetch files from Supabase storage and upload to GenAI for analysis
        # This ensures we always have access to files even if GenAI files expired
        try:
            uploaded_files = await archive_service.fetch_and_upload_files_from_storage(storage_paths)
        except Exception as e:
            print(f"Error fetching files from storage: {e}")
            # If we can't fetch files, just update metadata without regenerating summary
            update_response = supabase.table("archives").update(update_payload).eq("id", archive_id).execute()
            
            if not update_response.data:
                raise HTTPException(status_code=500, detail="Failed to update archive")
            
            updated_archive = update_response.data[0]
            updated_archive.pop("summary", None)
            updated_archive.pop("embedding", None)
            
            # Add file URIs
            file_uris = []
            if "storage_paths" in updated_archive and updated_archive["storage_paths"]:
                for storage_path in updated_archive["storage_paths"]:
                    try:
                        public_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
                        public_url = normalize_public_url(public_url_response)
                        if public_url:
                            file_uris.append(public_url)
                    except Exception as e:
                        print(f"Error generating public URL for {storage_path}: {e}")
            
            updated_archive["file_uris"] = file_uris
            return updated_archive
        
        # Use updated values or existing ones
        title = update_payload.get("title", existing_archive.get("title", ""))
        description = update_payload.get("description", existing_archive.get("description", ""))
        tags = update_payload.get("tags", existing_archive.get("tags", []))
        media_types = existing_archive.get("media_types", [])
        
        # Regenerate AI summary
        new_summary = await archive_service.analyze_content(
            uploaded_files=uploaded_files,
            title=title,
            media_types=media_types,
            tags=tags,
            description=description
        )
        
        # Generate new embedding
        new_embedding = await archive_service.generate_embedding(text=new_summary)
        
        # Update payload with new summary and embedding
        update_payload["summary"] = new_summary
        update_payload["embedding"] = new_embedding
        
        # Update in database
        update_response = supabase.table("archives").update(update_payload).eq("id", archive_id).execute()
        
        if not update_response.data:
            raise HTTPException(status_code=500, detail="Failed to update archive")
        
        updated_archive = update_response.data[0]
        
        # Remove summary and embedding from response (hidden from user)
        updated_archive.pop("summary", None)
        updated_archive.pop("embedding", None)
        
        # Add file URIs
        file_uris = []
        if "storage_paths" in updated_archive and updated_archive["storage_paths"]:
            for storage_path in updated_archive["storage_paths"]:
                try:
                    public_url_response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
                    public_url = normalize_public_url(public_url_response)
                    if public_url:
                        file_uris.append(public_url)
                except Exception as e:
                    print(f"Error generating public URL for {storage_path}: {e}")
        
        updated_archive["file_uris"] = file_uris
        
        return updated_archive
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update archive: {str(e)}"
        )

