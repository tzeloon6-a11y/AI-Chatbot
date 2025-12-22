from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class ArchiveCreate(BaseModel):
    title: str = Field(..., description="Title of the archive item")
    media_types: List[MediaType] = Field(..., description="List of media types in the archive")
    dates: Optional[List[datetime]] = Field(None, description="List of dates associated with the archive")
    tags: Optional[List[str]] = Field(default_factory=list, description="List of tags for categorization")
    description: Optional[str] = Field(None, description="Description of the archive content")


class ArchiveResponse(BaseModel):
    id: str = Field(..., description="Unique identifier for the archive")
    title: str = Field(..., description="Title of the archive item")
    media_types: List[MediaType] = Field(..., description="List of media types")
    dates: Optional[List[datetime]] = Field(None, description="List of dates")
    tags: Optional[List[str]] = Field(default_factory=list, description="List of tags")
    description: Optional[str] = Field(None, description="Description")
    # summary is hidden from users - stored in DB but not exposed in API
    file_uris: List[str] = Field(..., description="URIs of uploaded files in Google GenAI")
    storage_paths: List[str] = Field(..., description="Supabase storage paths for uploaded materials")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        from_attributes = True


class ArchiveUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Title of the archive item")
    dates: Optional[List[datetime]] = Field(None, description="List of dates associated with the archive")
    tags: Optional[List[str]] = Field(None, description="List of tags for categorization")
    description: Optional[str] = Field(None, description="Description of the archive content")

