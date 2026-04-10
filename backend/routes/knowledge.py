"""
Knowledge base API endpoints.
"""
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import anyio

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    CreateKnowledgeBaseRequest,
    UpdateKnowledgeBaseRequest,
    IndexingRequest,
    UploadFileResponse,
)
from knowledge.models import KnowledgeBaseInfo, DocumentInfo, DocumentStatus, IndexingStrategy
from services.knowledge_manager import KnowledgeManager
from services.document_indexer import DocumentIndexer

knowledge_router = APIRouter(prefix="/api/knowledge")


def get_knowledge_manager() -> KnowledgeManager:
    """Get KnowledgeManager instance."""
    return KnowledgeManager()


def get_document_indexer() -> DocumentIndexer:
    """Get DocumentIndexer instance."""
    return DocumentIndexer()


# =============================================================================
# Knowledge Base CRUD
# =============================================================================

@knowledge_router.post("", response_model=KnowledgeBaseInfo)
async def create_knowledge_base(request: CreateKnowledgeBaseRequest):
    """
    Create a new knowledge base.

    Args:
        request: CreateKnowledgeBaseRequest with name and optional description

    Returns:
        Created KnowledgeBaseInfo
    """
    km = get_knowledge_manager()
    kb = km.create_knowledge_base(name=request.name, description=request.description)
    return kb


@knowledge_router.get("", response_model=List[KnowledgeBaseInfo])
async def list_knowledge_bases():
    """
    List all knowledge bases.

    Returns:
        List of KnowledgeBaseInfo objects
    """
    km = get_knowledge_manager()
    return km.list_knowledge_bases()


@knowledge_router.get("/{kb_id}", response_model=KnowledgeBaseInfo)
async def get_knowledge_base(kb_id: str):
    """
    Get a knowledge base by ID.

    Args:
        kb_id: Knowledge base identifier

    Returns:
        KnowledgeBaseInfo with documents list
    """
    km = get_knowledge_manager()
    kb = km.get_knowledge_base(kb_id)

    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    return kb


@knowledge_router.put("/{kb_id}", response_model=KnowledgeBaseInfo)
async def update_knowledge_base(kb_id: str, request: UpdateKnowledgeBaseRequest):
    """
    Update knowledge base metadata.

    Args:
        kb_id: Knowledge base identifier
        request: UpdateKnowledgeBaseRequest

    Returns:
        Updated KnowledgeBaseInfo
    """
    km = get_knowledge_manager()

    indexing_strategy = None
    if request.indexing_strategy:
        if request.indexing_strategy == "incremental":
            indexing_strategy = IndexingStrategy.INCREMENTAL
        elif request.indexing_strategy == "full":
            indexing_strategy = IndexingStrategy.FULL

    kb = km.update_knowledge_base(
        kb_id=kb_id,
        name=request.name,
        description=request.description,
        indexing_strategy=indexing_strategy,
    )

    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    return kb


@knowledge_router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """
    Delete a knowledge base and all its data.

    This removes:
    - All vector embeddings from ChromaDB
    - All document files from storage
    - All metadata and chunk trackers

    Args:
        kb_id: Knowledge base identifier

    Returns:
        Success message
    """
    km = get_knowledge_manager()
    indexer = get_document_indexer()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    # Delete entire ChromaDB collection for this KB
    try:
        indexer.delete_knowledge_base_vectors(kb_id)
    except Exception as e:
        print(f"Warning: Failed to delete vector store: {e}")

    if not km.delete_knowledge_base(kb_id):
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    return {"success": True, "message": f"Knowledge base '{kb_id}' deleted"}


# =============================================================================
# Document Management
# =============================================================================

@knowledge_router.post("/{kb_id}/documents", response_model=UploadFileResponse)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """
    Upload a document to a knowledge base.

    Args:
        kb_id: Knowledge base identifier
        file: File to upload

    Returns:
        UploadFileResponse with document info
    """
    km = get_knowledge_manager()

    # Check if KB exists
    if not km.get_knowledge_base(kb_id):
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    import uuid

    doc_id = str(uuid.uuid4())

    # Read file content
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Save content and get hash
    content_hash = await km.save_document_content(kb_id, doc_id, file.filename, content)

    if not content_hash:
        raise HTTPException(status_code=500, detail="Failed to save document")

    # Create document record
    doc = DocumentInfo(
        id=doc_id,
        filename=file.filename,
        size=len(content),
        content_hash=content_hash,
    )

    km.add_document(kb_id, doc)

    return UploadFileResponse(
        document_id=doc_id,
        filename=file.filename,
        size=len(content),
        status="pending",
    )


@knowledge_router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """
    Delete a document from a knowledge base.

    This removes:
    - Document metadata from knowledge base
    - Document file from storage
    - Vector embeddings from ChromaDB
    - Chunk hashes from tracker

    Args:
        kb_id: Knowledge base identifier
        doc_id: Document identifier

    Returns:
        Success message
    """
    km = get_knowledge_manager()
    indexer = get_document_indexer()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    doc = km.get_document(kb_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Delete vector embeddings first
    try:
        indexer.delete_document_chunks(kb_id, doc_id)
    except Exception as e:
        print(f"Warning: Failed to delete vector chunks: {e}")

    # Remove document metadata and files
    if not km.remove_document(kb_id, doc_id):
        raise HTTPException(status_code=500, detail="Failed to delete document")

    return {"success": True, "message": f"Document '{doc_id}' deleted"}


# =============================================================================
# Indexing Control
# =============================================================================

@knowledge_router.post("/{kb_id}/index")
async def trigger_indexing(kb_id: str, request: IndexingRequest = None):
    """
    Trigger indexing for a knowledge base.

    This runs in the background to avoid blocking requests.

    Args:
        kb_id: Knowledge base identifier
        request: IndexingRequest with strategy (incremental/full)

    Returns:
        Status message
    """
    if request is None:
        request = IndexingRequest(strategy="incremental")

    km = get_knowledge_manager()
    indexer = get_document_indexer()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    # Determine strategy
    strategy = IndexingStrategy.INCREMENTAL
    if request.strategy == "full":
        strategy = IndexingStrategy.FULL

    # Get documents to index
    if request.document_ids:
        # Index specific documents
        docs = [km.get_document(kb_id, doc_id) for doc_id in request.document_ids]
        docs = [d for d in docs if d is not None]
    else:
        # Index all pending documents
        docs = [d for d in kb.documents if d.status != DocumentStatus.INDEXED]

    if not docs:
        return {
            "status": "no_documents",
            "message": "No documents to index",
            "total_chunks": kb.total_chunks,
        }

    # Run indexing (in production, use background tasks)
    try:
        total_chunks, new_chunks = indexer.index_documents(
            kb_id=kb_id,
            documents=docs,
            knowledge_manager=km,
            strategy=strategy,
        )

        km.update_last_indexed(kb_id)

        return {
            "status": "success",
            "message": f"Indexed {new_chunks} new chunks ({total_chunks} total)",
            "total_chunks": total_chunks,
            "new_chunks": new_chunks,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@knowledge_router.get("/{kb_id}/index/status")
async def get_indexing_status(kb_id: str):
    """
    Get indexing status for a knowledge base.

    Args:
        kb_id: Knowledge base identifier

    Returns:
        Indexing status with document breakdown
    """
    km = get_knowledge_manager()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    pending = sum(1 for d in kb.documents if d.status == DocumentStatus.PENDING)
    indexing = sum(1 for d in kb.documents if d.status == DocumentStatus.INDEXING)
    indexed = sum(1 for d in kb.documents if d.status == DocumentStatus.INDEXED)
    failed = sum(1 for d in kb.documents if d.status == DocumentStatus.FAILED)

    return {
        "kb_id": kb_id,
        "total_documents": len(kb.documents),
        "total_chunks": kb.total_chunks,
        "status_breakdown": {
            "pending": pending,
            "indexing": indexing,
            "indexed": indexed,
            "failed": failed,
        },
        "indexing_strategy": kb.indexing_strategy,
        "last_indexed_at": kb.last_indexed_at,
    }


@knowledge_router.get("/{kb_id}/chunks")
async def get_chunk_status(kb_id: str):
    """
    Get detailed chunk status for a knowledge base.

    Args:
        kb_id: Knowledge base identifier

    Returns:
        Detailed chunk information
    """
    km = get_knowledge_manager()
    indexer = get_document_indexer()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    # Get stats from indexer
    try:
        stats = indexer.get_stats(kb_id)
    except Exception:
        stats = {"indexed_chunks": 0, "vector_count": 0}

    return {
        "kb_id": kb_id,
        "total_chunks": kb.total_chunks,
        "indexed_chunks": stats.get("indexed_chunks", 0),
        "vector_count": stats.get("vector_count", 0),
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "error_message": d.error_message,
            }
            for d in kb.documents
        ],
    }


# =============================================================================
# Search (for testing/debugging)
# =============================================================================

@knowledge_router.get("/{kb_id}/search")
async def search_knowledge_base(kb_id: str, query: str, k: int = 3):
    """
    Search within a knowledge base.

    Args:
        kb_id: Knowledge base identifier
        query: Search query
        k: Number of results

    Returns:
        Search results
    """
    km = get_knowledge_manager()

    kb = km.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    indexer = get_document_indexer()
    results = indexer.search(kb_id, query, k=k)

    return {
        "query": query,
        "results": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in results
        ],
    }


@knowledge_router.post("/search/multi")
async def search_multiple_knowledge_bases(
    query: str,
    kb_ids: List[str],
    k_per_kb: int = 2,
):
    """
    Search across multiple knowledge bases.

    Args:
        query: Search query
        kb_ids: List of knowledge base IDs to search
        k_per_kb: Number of results per KB

    Returns:
        Combined search results
    """
    indexer = get_document_indexer()
    results = indexer.search_multi(kb_ids, query, k_per_kb)

    return {
        "query": query,
        "kb_ids": kb_ids,
        "results": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in results
        ],
    }
