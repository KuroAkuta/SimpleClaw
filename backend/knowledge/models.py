"""
Pydantic models for knowledge base functionality.
"""
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class IndexingStrategy(str, Enum):
    """Strategy for indexing documents."""
    INCREMENTAL = "incremental"  # Only index new/changed documents
    FULL = "full"                # Delete and reindex everything


class DocumentStatus(str, Enum):
    """Status of document indexing."""
    PENDING = "pending"      # Uploaded, waiting for indexing
    INDEXING = "indexing"    # Currently being indexed
    INDEXED = "indexed"      # Successfully indexed
    FAILED = "failed"        # Indexing failed


class DocumentInfo(BaseModel):
    """Information about a single document."""
    id: str
    filename: str
    size: int
    content_hash: str           # For detecting content changes
    status: DocumentStatus = DocumentStatus.PENDING
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def model_dump(self, *args, **kwargs):
        """Override to handle datetime serialization."""
        data = super().model_dump(*args, **kwargs)
        # Convert datetime to ISO format strings
        if "created_at" in data and isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"].isoformat()
        if "updated_at" in data and isinstance(data["updated_at"], datetime):
            data["updated_at"] = data["updated_at"].isoformat()
        return data


class KnowledgeBaseInfo(BaseModel):
    """Knowledge base metadata."""
    id: str
    name: str
    description: Optional[str] = None
    documents: List[DocumentInfo] = []
    total_chunks: int = 0
    indexing_strategy: IndexingStrategy = IndexingStrategy.INCREMENTAL
    last_indexed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def model_dump(self, *args, **kwargs):
        """Override to handle datetime serialization."""
        data = super().model_dump(*args, **kwargs)
        for key in ["created_at", "updated_at", "last_indexed_at"]:
            if key in data and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        # Handle documents list
        if "documents" in data:
            data["documents"] = [
                doc.model_dump() if hasattr(doc, "model_dump") else doc
                for doc in data["documents"]
            ]
        return data


class ChatKnowledgeSelection(BaseModel):
    """Selected knowledge bases for a chat session."""
    enabled_knowledge_bases: List[str]  # List of knowledge base IDs
