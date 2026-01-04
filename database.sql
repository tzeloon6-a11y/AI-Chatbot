-- Database Schema for AI-Chatbot Project
-- Generated from Supabase project: ai search for curators (huqfxrgcjpvxhgwwgysm)
-- Last updated: 2025-01-27

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- ARCHIVES TABLE
-- ============================================================================
-- Stores digital heritage archive items with vector embeddings for AI search
-- Purpose: Main table for storing cultural heritage materials with semantic search capabilities
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.archives (
    -- Primary identifier
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Content fields
    title TEXT NOT NULL,
    description TEXT,  -- Nullable
    summary TEXT NOT NULL,
    
    -- Vector embedding for semantic search (pgvector extension)
    embedding vector NOT NULL,
    
    -- Metadata arrays
    media_types TEXT[] NOT NULL,      -- e.g., ['image', 'video', 'document']
    tags TEXT[],                       -- Nullable, e.g., ['batik', 'kelantan', 'traditional']
    dates TIMESTAMPTZ[],               -- Nullable, array of timestamps
    
    -- Storage references
    storage_paths TEXT[] NOT NULL,     -- Array of file paths in Supabase Storage
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE OPTIMIZATION
-- ============================================================================

-- Primary key index (automatically created by PostgreSQL)
-- CREATE UNIQUE INDEX archives_pkey ON public.archives USING btree (id);

-- GIN index for tags array (enables fast tag searches and filtering)
CREATE INDEX IF NOT EXISTS archives_tags_idx 
    ON public.archives USING gin (tags);

-- GIN index for media_types array (enables fast media type filtering)
CREATE INDEX IF NOT EXISTS archives_media_types_idx 
    ON public.archives USING gin (media_types);

-- GIN index for dates array (enables fast date range queries)
CREATE INDEX IF NOT EXISTS archives_dates_idx 
    ON public.archives USING gin (dates);

-- HNSW index for vector embeddings (enables fast similarity search)
-- Uses cosine distance for semantic similarity matching
CREATE INDEX IF NOT EXISTS archives_embedding_idx 
    ON public.archives USING hnsw (embedding vector_cosine_ops);

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. The vector extension (pgvector) is used for storing and searching embeddings
-- 2. GIN indexes are optimal for array column searches (tags, media_types, dates)
-- 3. HNSW (Hierarchical Navigable Small World) index provides approximate nearest 
--    neighbor search on vectors with high performance
-- 4. RLS (Row Level Security) is currently disabled on this table
-- 5. The embedding dimension is determined by the model used (typically 768 or 1536)
-- ============================================================================
