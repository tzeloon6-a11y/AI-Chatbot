import asyncio
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from google import genai
from google.genai import types
from fastapi import UploadFile, HTTPException
from supabase import StorageException

from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.schemas.archive import ArchiveResponse


class ArchiveService:
    """
    Service for handling archive operations including file upload,
    content analysis, and embedding generation using Google GenAI.
    """
    
    def __init__(self):
        """Initialize Google GenAI client."""
        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self.model = "gemini-2.5-flash-lite"
        self.embedding_model = "text-embedding-004"
        self.supabase_client = get_supabase_client()
        if not settings.SUPABASE_STORAGE_BUCKET:
            raise ValueError("SUPABASE_STORAGE_BUCKET is not configured")
        self.storage_bucket = settings.SUPABASE_STORAGE_BUCKET
    
    @property
    def client(self):
        """Lazy initialization of Google GenAI client."""
        if self._client is None:
            if not settings.GOOGLE_GENAI_API_KEY:
                raise ValueError("GOOGLE_GENAI_API_KEY is not configured")
            self._client = genai.Client(api_key=settings.GOOGLE_GENAI_API_KEY)
        return self._client
    
    def _create_temp_file(self, content: bytes, suffix: str) -> str:
        """Persist bytes to a temporary file and return its path."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            return tmp_file.name
    
    def _cleanup_temp_file(self, file_path: str):
        """Remove temporary file."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            # Log error but don't fail
            print(f"Error cleaning up temp file {file_path}: {e}")
    
    def _build_storage_path(self, filename: Optional[str]) -> str:
        """Generate a safe storage path for Supabase storage."""
        base_name = filename or "uploaded_file"
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", base_name)
        return f"archives/{uuid4().hex}/{safe_name}"

    async def _upload_file_to_supabase_storage(
        self,
        storage_path: str,
        content: bytes,
        mime_type: Optional[str],
    ) -> str:
        """Upload file content to Supabase Storage and return the storage path."""
        storage_bucket = self.supabase_client.storage.from_(self.storage_bucket)
        loop = asyncio.get_event_loop()

        def _upload():
            storage_bucket.upload(
                storage_path,
                content,
                file_options={
                    "content-type": mime_type or "application/octet-stream",
                },
            )
            return storage_path

        try:
            return await loop.run_in_executor(self._executor, _upload)
        except StorageException as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file to storage: {exc.message}",
            ) from exc
    
    async def _download_file_from_supabase_storage(
        self,
        storage_path: str
    ) -> bytes:
        """Download file content from Supabase Storage."""
        storage_bucket = self.supabase_client.storage.from_(self.storage_bucket)
        loop = asyncio.get_event_loop()

        def _download():
            response = storage_bucket.download(storage_path)
            return response

        try:
            return await loop.run_in_executor(self._executor, _download)
        except StorageException as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to download file from storage: {exc.message}",
            ) from exc
    
    async def _upload_file_content_to_genai(
        self,
        content: bytes,
        filename: str,
        mime_type: str
    ):
        """
        Upload file content to Google GenAI and return the file object.
        
        Args:
            content: File content as bytes
            filename: Name of the file
            mime_type: MIME type of the file
            
        Returns:
            Uploaded file object from Google GenAI
        """
        suffix = Path(filename).suffix
        temp_path = self._create_temp_file(content, suffix)
        
        try:
            loop = asyncio.get_event_loop()

            def upload_file():
                return self.client.files.upload(
                    file=temp_path,
                    config=types.UploadFileConfig(
                        display_name=filename,
                        mime_type=mime_type,
                    ),
                )

            uploaded_file = await loop.run_in_executor(
                self._executor,
                upload_file,
            )

            # Wait for file to be processed
            max_wait_time = 300
            wait_interval = 2
            elapsed_time = 0

            while uploaded_file.state == "PROCESSING" and elapsed_time < max_wait_time:
                await asyncio.sleep(wait_interval)
                elapsed_time += wait_interval

                file_name = uploaded_file.name

                def get_file():
                    return self.client.files.get(name=file_name)

                uploaded_file = await loop.run_in_executor(
                    self._executor,
                    get_file,
                )

            if uploaded_file.state != "ACTIVE":
                raise HTTPException(
                    status_code=500,
                    detail=f"File {filename} failed to process. State: {uploaded_file.state}",
                )

            return uploaded_file

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file to GenAI: {exc}",
            ) from exc
        finally:
            # Cleanup temporary file
            self._cleanup_temp_file(temp_path)
    
    async def fetch_and_upload_files_from_storage(
        self,
        storage_paths: List[str]
    ) -> List:
        """
        Fetch files from Supabase storage and upload them to Google GenAI.
        This is used when GenAI files have expired and we need to regenerate analysis.
        
        Args:
            storage_paths: List of Supabase storage paths
            
        Returns:
            List of uploaded file objects from Google GenAI
        """
        if not storage_paths:
            raise HTTPException(status_code=400, detail="No storage paths provided")

        uploaded_files = []
        
        for storage_path in storage_paths:
            try:
                # Download file from Supabase
                content = await self._download_file_from_supabase_storage(storage_path)
                
                # Extract filename and determine MIME type
                filename = storage_path.split('/')[-1]
                
                # Infer MIME type from filename extension
                suffix = Path(filename).suffix.lower()
                mime_type_map = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.mp4': 'video/mp4',
                    '.mov': 'video/quicktime',
                    '.avi': 'video/x-msvideo',
                    '.mp3': 'audio/mpeg',
                    '.wav': 'audio/wav',
                    '.pdf': 'application/pdf',
                    '.doc': 'application/msword',
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    '.txt': 'text/plain',
                }
                mime_type = mime_type_map.get(suffix, 'application/octet-stream')
                
                # Upload to GenAI
                uploaded_file = await self._upload_file_content_to_genai(
                    content=content,
                    filename=filename,
                    mime_type=mime_type
                )
                
                uploaded_files.append(uploaded_file)
                
            except Exception as e:
                print(f"Error processing file {storage_path}: {e}")
                # Continue with other files
                continue
        
        if not uploaded_files:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload any files to GenAI from storage"
            )
        
        return uploaded_files
    
    def _get_comprehensive_analysis_prompt(
        self,
        title: str,
        media_types: List[str],
        tags: List[str],
        description: str
    ) -> str:
        """
        Generate a comprehensive prompt for content analysis based on prompt engineering best practices.
        
        Args:
            title: Title of the archive
            media_types: List of media types
            tags: List of tags
            description: User-provided description
            
        Returns:
            Enhanced comprehensive analysis prompt following best practices
        """
        media_types_str = ", ".join(media_types)
        tags_str = ", ".join(tags) if tags else "None provided"
        
        # Build media-specific instructions
        media_instructions = []
        if "image" in media_types:
            media_instructions.append(
                "**Images**: Analyze visual composition including objects, people, settings, text overlay, "
                "color schemes, lighting, perspective, mood, and any symbols or logos. Identify any readable text, "
                "brands, locations, or distinctive visual elements. Note the style (photography, illustration, diagram, etc.) "
                "and potential purpose or context."
            )
        if "video" in media_types:
            media_instructions.append(
                "**Videos**: Analyze visual and auditory elements including scenes, actions, dialogue, narration, "
                "background music, sound effects, pacing, transitions, camera movements, settings, participants, "
                "narrative structure, key moments, and overall message or story arc."
            )
        if "audio" in media_types:
            media_instructions.append(
                "**Audio**: Analyze spoken content including speakers, topics discussed, tone and emotion, "
                "background sounds, music (if any), key messages, questions and answers, important statements or quotes, "
                "contextual cues, and overall purpose or theme."
            )
        if "document" in media_types:
            media_instructions.append(
                "**Documents**: Extract key information including main topics, headings, bullet points, data tables, "
                "statistics, dates, names, organizations, conclusions, recommendations, and structural organization. "
                "Identify document type (report, article, contract, etc.) and summarize content systematically."
            )
        
        media_guidance = "\n".join(f"- {instr}" for instr in media_instructions) if media_instructions else "- Analyze all media types comprehensively"
        
        prompt = f"""# Role and Context

You are a Malaysian cultural heritage expert and curator assistant specializing in archiving and documenting Malaysian heritage materials. You are analyzing content for an AI-powered heritage search system used by curators and researchers.

**Application Context**: This is a heritage archiving system for Malaysian cultural materials including traditional crafts, historical artifacts, cultural practices, architecture, textiles, art, and documentation.

# Archive Information

**Title**: {title}
**Media Types**: {media_types_str}
**Tags**: {tags_str}
**Description**: {description if description else "Not provided"}

---

# Your Task

Analyze the uploaded materials and create a CONCISE, searchable summary that captures the essential heritage information. This summary will be used for:
1. AI-powered semantic search to help curators find relevant materials
2. Quick overview of the archive content
3. Generating text embeddings for search functionality

**CRITICAL LENGTH REQUIREMENT**: Your summary MUST be between 300-800 words maximum. This limit ensures optimal embedding generation (Google text-embedding-004 has ~1500 word limit, but we need buffer space).

---

# Analysis Instructions

{media_guidance}

**Focus on Heritage-Specific Information**:
- **Cultural significance**: Historical, cultural, or traditional importance
- **Geographic origin**: Specific Malaysian states, regions, cities, or communities
- **Time period**: Era, decade, or specific dates when relevant
- **Cultural context**: Ethnic group, tradition, ceremony, or cultural practice
- **Materials/techniques**: Traditional craftsmanship methods, materials used
- **People/organizations**: Artists, craftspeople, cultural institutions
- **Visual elements**: Colors, patterns, motifs, symbols (for images/art)
- **Condition/provenance**: State of preservation, origin, or ownership history

---

# Output Format

Provide a well-structured, concise summary organized as follows:

**1. Overview** (2-3 sentences):
Brief description of what this archive contains and its primary subject.

**2. Heritage Details**:
- **Name/Type**: What is this item/material called? What category does it belong to?
- **Description**: Physical characteristics, visual elements, key features
- **Cultural Context**: Malaysian heritage relevance, ethnic/regional associations, traditional significance
- **Location/Origin**: Geographic location, state, region, or community
- **Time Period**: When it's from or when documented (if applicable)
- **Materials/Technique**: Craftsmanship methods, materials, artistic techniques (if applicable)

**3. Key Content**:
List the most important facts, observations, or notable elements found in the materials. Be specific and factual.

**4. Search Keywords**:
Provide relevant keywords that would help curators find this archive (e.g., "batik", "Penang", "traditional weaving", "Malay architecture").

---

# Quality Guidelines

✅ **DO**:
- Be concise and information-dense (300-800 words MAXIMUM)
- Use specific Malaysian heritage terminology
- Include geographic locations (states, cities, regions)
- Mention ethnic groups, cultural practices, traditional names
- Note time periods, dates, or eras
- Describe visual/physical characteristics clearly
- Focus on factual, searchable information
- Use heritage curator vocabulary

❌ **DON'T**:
- Exceed 800 words (CRITICAL - embedding limit)
- Write long, flowery descriptions
- Include unnecessary commentary or analysis
- Repeat the same information multiple times
- Use vague generalizations
- Include meta-commentary about your analysis process

---

# Example Structure (Reference Only)

**Overview**: This archive contains photographs and documentation of traditional Peranakan beaded slippers (kasut manek) from Melaka, showcasing intricate needlework techniques from the early 20th century.

**Heritage Details**:
- **Name/Type**: Kasut Manek (Peranakan Beaded Slippers), traditional footwear
- **Description**: Handcrafted slippers featuring colorful glass bead embroidery with floral and phoenix motifs on velvet base
- **Cultural Context**: Peranakan/Straits Chinese heritage, traditionally worn for weddings and special occasions
- **Location/Origin**: Melaka, Malaysia
- **Time Period**: Early 1900s (circa 1920s-1930s)
- **Materials/Technique**: Glass seed beads, velvet, silk thread, hand-beading needlework

**Key Content**: [Specific details from the actual files...]

**Search Keywords**: Peranakan, kasut manek, beaded slippers, Melaka, Straits Chinese, traditional footwear, handcraft, embroidery, heritage craft, Nyonya culture

Begin your analysis now. Remember: MAXIMUM 800 WORDS."""
        
        return prompt.strip()
    
    async def upload_files_to_genai(
        self,
        files: List[UploadFile]
    ) -> tuple[List, List[str], List[str]]:
        """
        Upload files to Supabase storage and Google GenAI, returning file objects and metadata.
        
        Args:
            files: List of uploaded files
            
        Returns:
            Tuple containing:
                - List of uploaded file objects from Google GenAI
                - List of Supabase storage paths
                - List of Google GenAI file identifiers
            
        Raises:
            HTTPException: If file upload fails
        """
        if not files:
            raise HTTPException(status_code=400, detail="At least one file must be uploaded")

        uploaded_files: List = []
        storage_paths: List[str] = []
        genai_file_ids: List[str] = []
        temp_file_paths: List[str] = []
        
        try:
            for file in files:
                content = await file.read()
                mime_type = file.content_type or "application/octet-stream"
                storage_path = await self._upload_file_to_supabase_storage(
                    self._build_storage_path(file.filename),
                    content,
                    mime_type,
                )
                storage_paths.append(storage_path)

                suffix = Path(file.filename or "").suffix
                temp_path = self._create_temp_file(content, suffix)
                temp_file_paths.append(temp_path)

                try:
                    loop = asyncio.get_event_loop()

                    def upload_file():
                        return self.client.files.upload(
                            file=temp_path,
                            config=types.UploadFileConfig(
                                display_name=file.filename or "uploaded_file",
                                mime_type=mime_type,
                            ),
                        )

                    uploaded_file = await loop.run_in_executor(
                        self._executor,
                        upload_file,
                    )

                    max_wait_time = 300
                    wait_interval = 2
                    elapsed_time = 0

                    while uploaded_file.state == "PROCESSING" and elapsed_time < max_wait_time:
                        await asyncio.sleep(wait_interval)
                        elapsed_time += wait_interval

                        file_name = uploaded_file.name

                        def get_file():
                            return self.client.files.get(name=file_name)

                        uploaded_file = await loop.run_in_executor(
                            self._executor,
                            get_file,
                        )

                    if uploaded_file.state != "ACTIVE":
                        raise HTTPException(
                            status_code=500,
                            detail=f"File {file.filename} failed to process. State: {uploaded_file.state}",
                        )

                    uploaded_files.append(uploaded_file)
                    genai_file_ids.append(uploaded_file.name)

                except Exception as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload file {file.filename}: {exc}",
                    ) from exc

            return uploaded_files, storage_paths, genai_file_ids
            
        finally:
            # Cleanup temporary files
            for temp_path in temp_file_paths:
                self._cleanup_temp_file(temp_path)
    
    async def generate_metadata_suggestions(
        self,
        uploaded_files: List,
        media_types: List[str]
    ) -> dict:
        """
        Generate metadata suggestions (title, tags, description) from uploaded content.
        
        Args:
            uploaded_files: List of uploaded file objects from Google GenAI
            media_types: List of media types
            
        Returns:
            Dictionary with 'title', 'tags', and 'description'
            
        Raises:
            HTTPException: If generation fails
        """
        try:
            # Build prompt for metadata generation
            media_types_str = ", ".join(media_types)
            
            prompt = f"""# Role and Context

You are a Malaysian cultural heritage expert analyzing materials for an archiving system. You need to generate metadata (title, tags, and description) based on the uploaded content.

**Media Types**: {media_types_str}

---

# Your Task

Analyze the uploaded materials and generate:
1. **Title**: A concise, descriptive title (5-10 words maximum)
2. **Tags**: 5-10 relevant keywords/tags for categorization
3. **Description**: A brief description (2-3 sentences, 50-100 words)

Focus on:
- Malaysian cultural heritage context
- Geographic locations (states, cities, regions)
- Cultural elements (ethnic groups, traditions, practices)
- Visual/content characteristics
- Time period (if evident)
- Materials/techniques (if applicable)

---

# Output Format

Provide your response in the following JSON format ONLY (no additional text):

{{
  "title": "Concise descriptive title here",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "description": "Brief 2-3 sentence description here."
}}

**CRITICAL**: Return ONLY valid JSON. No markdown code blocks, no explanations, no extra text.

Begin your analysis now."""
            
            # Build content parts
            contents = [prompt]
            for uploaded_file in uploaded_files:
                contents.append(uploaded_file)
            
            # Generate metadata (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            
            def generate_content():
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=1024,
                        top_p=0.95,
                        top_k=40,
                        response_mime_type="application/json",
                    )
                )
            
            response = await loop.run_in_executor(
                self._executor,
                generate_content
            )
            
            if not response.text:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate metadata. Empty response from model."
                )
            
            # Parse JSON response
            try:
                metadata = json.loads(response.text)
                # Validate structure
                if not all(key in metadata for key in ["title", "tags", "description"]):
                    raise ValueError("Missing required fields in metadata")
                return metadata
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing metadata JSON: {e}")
                print(f"Response text: {response.text}")
                # Return fallback metadata
                return {
                    "title": "Uploaded Heritage Material",
                    "tags": ["heritage", "malaysian culture"],
                    "description": "Heritage material uploaded for archival purposes."
                }
            
        except Exception as e:
            print(f"Error generating metadata: {str(e)}")
            # Return fallback metadata instead of raising exception
            return {
                "title": "Uploaded Heritage Material",
                "tags": ["heritage", "malaysian culture"],
                "description": "Heritage material uploaded for archival purposes."
            }
    
    async def analyze_content(
        self,
        uploaded_files: List,
        title: str,
        media_types: List[str],
        tags: List[str],
        description: str
    ) -> str:
        """
        Analyze uploaded content using Google GenAI and generate comprehensive summary.
        
        Args:
            uploaded_files: List of uploaded file objects from Google GenAI
            title: Title of the archive
            media_types: List of media types
            tags: List of tags
            description: User-provided description
            
        Returns:
            Comprehensive analysis summary as text
            
        Raises:
            HTTPException: If analysis fails
        """
        try:
            # Build content parts
            contents = []
            
            # Add the comprehensive prompt
            prompt = self._get_comprehensive_analysis_prompt(
                title=title,
                media_types=media_types,
                tags=tags,
                description=description
            )
            contents.append(prompt)
            
            # Add all uploaded files - file objects can be passed directly
            for uploaded_file in uploaded_files:
                contents.append(uploaded_file)
            
            # Generate content analysis (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            
            def generate_content():
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.2,  # Lower temperature for more focused, deterministic analysis
                        max_output_tokens=8192,  # Allow comprehensive responses
                        top_p=0.95,  # Nucleus sampling for diverse but focused responses
                        top_k=40,  # Limit vocabulary for more relevant outputs
                    )
                )
            
            response = await loop.run_in_executor(
                self._executor,
                generate_content
            )
            
            if not response.text:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate analysis. Empty response from model."
                )
            
            return response.text
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze content: {str(e)}"
            )
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate text embedding using Google GenAI embedding model.
        
        Args:
            text: Text to embed
            
        Returns:
            List of float values representing the embedding vector
            
        Raises:
            HTTPException: If embedding generation fails
        """
        try:
            # Generate embedding (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            
            def embed_content():
                return self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                    )
                )
            
            response = await loop.run_in_executor(
                self._executor,
                embed_content
            )
            
            if not response.embeddings or len(response.embeddings) == 0:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate embedding. Empty response."
                )
            
            # Return the embedding values
            return response.embeddings[0].values
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate embedding: {str(e)}"
            )
    
    async def _persist_archive_record(
        self,
        *,
        title: str,
        description: Optional[str],
        summary: str,
        embedding: List[float],
        media_types: List[str],
        tags: List[str],
        dates: List[datetime],
        storage_paths: List[str],
    ) -> dict:
        payload = {
            "title": title,
            "description": description or None,
            "summary": summary,
            "embedding": embedding,
            "media_types": media_types,
            "tags": tags if tags else [],
            "dates": [dt.isoformat() for dt in dates] if dates else [],
            "storage_paths": storage_paths,
        }

        loop = asyncio.get_event_loop()

        def insert_record() -> dict:
            # In Supabase Python v2.x+, insert returns all fields by default
            response = (
                self.supabase_client.table("archives")
                .insert(payload)
                .execute()
            )
            data = response.data or []
            if not data:
                raise RuntimeError("Supabase insert returned no data")
            
            record = data[0]
            
            # Parse embedding if it's returned as a string (Supabase vector serialization)
            if "embedding" in record and isinstance(record["embedding"], str):
                try:
                    record["embedding"] = json.loads(record["embedding"])
                except (json.JSONDecodeError, TypeError):
                    # If it fails, keep the original value
                    pass
            
            return record

        try:
            return await loop.run_in_executor(self._executor, insert_record)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store archive metadata: {exc}",
            ) from exc
    
    async def process_archive(
        self,
        files: List[UploadFile],
        title: str,
        media_types: List[str],
        tags: List[str],
        description: str,
        dates: Optional[List[datetime]] = None,
    ) -> ArchiveResponse:
        """Complete archive processing pipeline."""

        uploaded_files, storage_paths, _ = await self.upload_files_to_genai(files)
        file_uris = [file_obj.uri for file_obj in uploaded_files]

        summary = await self.analyze_content(
            uploaded_files=uploaded_files,
            title=title,
            media_types=media_types,
            tags=tags,
            description=description,
        )

        embedding = await self.generate_embedding(text=summary)

        archive_record = await self._persist_archive_record(
            title=title,
            description=description,
            summary=summary,
            embedding=embedding,
            media_types=media_types,
            tags=tags,
            dates=dates or [],
            storage_paths=storage_paths,
        )

        archive_record["file_uris"] = file_uris
        archive_record.setdefault("storage_paths", storage_paths)

        return ArchiveResponse(**archive_record)

