"""
Pydantic schemas for request/response models.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoints."""
    message: str
    session_id: Optional[str] = None
    images: Optional[List[str]] = None  # List of base64 encoded images
    enabled_knowledge_bases: List[str] = []  # Knowledge bases to use for RAG


class ChatResponse(BaseModel):
    """Response model for non-streaming chat."""
    session_id: str
    message: str


class ToolConfirmRequest(BaseModel):
    """Request model for tool confirmation."""
    session_id: str
    action: str  # "confirm" or "reject"


class SessionInfo(BaseModel):
    """Session information for list response."""
    id: str
    created: str


class SessionsResponse(BaseModel):
    """Response model for session list."""
    sessions: List[SessionInfo]


class CreateSessionResponse(BaseModel):
    """Response model for session creation."""
    session_id: str


class DeleteSessionResponse(BaseModel):
    """Response model for session deletion."""
    success: bool


class ToolPendingResponse(BaseModel):
    """Response model for pending tool calls."""
    has_pending: bool
    tool_calls: List[dict]
    confirmed: bool


class ToolConfirmResponse(BaseModel):
    """Response model for tool confirmation."""
    success: bool
    status: str
    message: str


# =============================================================================
# Knowledge Base Schemas
# =============================================================================

class CreateKnowledgeBaseRequest(BaseModel):
    """Request model for creating a knowledge base."""
    name: str
    description: Optional[str] = None


class UpdateKnowledgeBaseRequest(BaseModel):
    """Request model for updating a knowledge base."""
    name: Optional[str] = None
    description: Optional[str] = None
    indexing_strategy: Optional[str] = None  # "incremental" or "full"


class IndexingRequest(BaseModel):
    """Request model for triggering indexing."""
    strategy: str = "incremental"  # "incremental" or "full"
    document_ids: Optional[List[str]] = None  # Specific docs to index


class UploadFileResponse(BaseModel):
    """Response model for file upload."""
    document_id: str
    filename: str
    size: int
    status: str
