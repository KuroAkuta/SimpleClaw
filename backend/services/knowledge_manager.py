"""
Knowledge Manager service for CRUD operations on knowledge bases.
"""
import uuid
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles

from knowledge.models import (
    KnowledgeBaseInfo,
    DocumentInfo,
    DocumentStatus,
    IndexingStrategy,
)


class KnowledgeManager:
    """
    Manages knowledge base CRUD operations and metadata.

    Responsibilities:
    - Create, read, update, delete knowledge bases
    - Upload and manage documents
    - Persist metadata to disk
    """

    def __init__(self, storage_dir: str = None):
        """
        Initialize the knowledge manager.

        Args:
            storage_dir: Directory for storing knowledge base data
        """
        if storage_dir is None:
            self.storage_dir = Path(__file__).parent.parent / "storage" / "knowledge"
        else:
            self.storage_dir = Path(storage_dir)

        self.docs_dir = self.storage_dir / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        self._knowledge_bases: Dict[str, KnowledgeBaseInfo] = self._load_metadata()

    def _load_metadata(self) -> Dict[str, KnowledgeBaseInfo]:
        """Load knowledge base metadata from file."""
        meta_file = self.storage_dir / "knowledge_bases.json"
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                return {kb["id"]: KnowledgeBaseInfo(**kb) for kb in data}
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_metadata(self):
        """Save knowledge base metadata to file."""
        meta_file = self.storage_dir / "knowledge_bases.json"
        data = [kb.model_dump() for kb in self._knowledge_bases.values()]
        meta_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def create_knowledge_base(
        self, name: str, description: Optional[str] = None
    ) -> KnowledgeBaseInfo:
        """
        Create a new knowledge base.

        Args:
            name: Name of the knowledge base
            description: Optional description

        Returns:
            Created KnowledgeBaseInfo object
        """
        kb = KnowledgeBaseInfo(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
        )
        self._knowledge_bases[kb.id] = kb

        # Create document directory for this KB
        (self.docs_dir / kb.id).mkdir(parents=True, exist_ok=True)

        self._save_metadata()
        return kb

    def get_knowledge_base(self, kb_id: str) -> Optional[KnowledgeBaseInfo]:
        """
        Get a knowledge base by ID.

        Args:
            kb_id: Knowledge base identifier

        Returns:
            KnowledgeBaseInfo or None if not found
        """
        return self._knowledge_bases.get(kb_id)

    def list_knowledge_bases(self) -> List[KnowledgeBaseInfo]:
        """
        List all knowledge bases.

        Returns:
            List of KnowledgeBaseInfo objects
        """
        return list(self._knowledge_bases.values())

    def update_knowledge_base(
        self,
        kb_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        indexing_strategy: Optional[IndexingStrategy] = None,
    ) -> Optional[KnowledgeBaseInfo]:
        """
        Update knowledge base metadata.

        Args:
            kb_id: Knowledge base identifier
            name: New name (optional)
            description: New description (optional)
            indexing_strategy: New indexing strategy (optional)

        Returns:
            Updated KnowledgeBaseInfo or None if not found
        """
        if kb_id not in self._knowledge_bases:
            return None

        kb = self._knowledge_bases[kb_id]
        if name is not None:
            kb.name = name
        if description is not None:
            kb.description = description
        if indexing_strategy is not None:
            kb.indexing_strategy = indexing_strategy

        kb.updated_at = datetime.now()
        self._save_metadata()
        return kb

    def delete_knowledge_base(self, kb_id: str) -> bool:
        """
        Delete a knowledge base and all its data.

        Args:
            kb_id: Knowledge base identifier

        Returns:
            True if deleted, False if not found
        """
        if kb_id not in self._knowledge_bases:
            return False

        kb = self._knowledge_bases[kb_id]

        # Delete document files
        kb_docs_dir = self.docs_dir / kb_id
        if kb_docs_dir.exists():
            import shutil
            shutil.rmtree(kb_docs_dir)

        # Delete metadata files
        for file in self.storage_dir.glob(f"{kb_id}_*"):
            file.unlink()

        del self._knowledge_bases[kb_id]
        self._save_metadata()
        return True

    def add_document(self, kb_id: str, document: DocumentInfo) -> Optional[DocumentInfo]:
        """
        Add a document to a knowledge base.

        Args:
            kb_id: Knowledge base identifier
            document: DocumentInfo object

        Returns:
            Added DocumentInfo or None if KB not found
        """
        if kb_id not in self._knowledge_bases:
            return None

        self._knowledge_bases[kb_id].documents.append(document)
        self._knowledge_bases[kb_id].updated_at = datetime.now()
        self._save_metadata()
        return document

    def get_document(self, kb_id: str, doc_id: str) -> Optional[DocumentInfo]:
        """
        Get a document from a knowledge base.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier

        Returns:
            DocumentInfo or None if not found
        """
        if kb_id not in self._knowledge_bases:
            return None

        for doc in self._knowledge_bases[kb_id].documents:
            if doc.id == doc_id:
                return doc
        return None

    def update_document_status(
        self,
        kb_id: str,
        doc_id: str,
        status: DocumentStatus,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Optional[DocumentInfo]:
        """
        Update document indexing status.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier
            status: New status
            chunk_count: Number of chunks (optional)
            error_message: Error message if failed (optional)

        Returns:
            Updated DocumentInfo or None if not found
        """
        doc = self.get_document(kb_id, doc_id)
        if doc is None:
            return None

        doc.status = status
        doc.updated_at = datetime.now()
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        # Clear error_message when status is INDEXED, otherwise set it if provided
        if status == DocumentStatus.INDEXED:
            doc.error_message = None
        elif error_message is not None:
            doc.error_message = f'(Recent error): {error_message}'

        self._save_metadata()
        return doc

    def remove_document(self, kb_id: str, doc_id: str) -> bool:
        """
        Remove a document from a knowledge base.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier

        Returns:
            True if removed, False if not found
        """
        if kb_id not in self._knowledge_bases:
            return False

        kb = self._knowledge_bases[kb_id]
        original_count = len(kb.documents)
        kb.documents = [d for d in kb.documents if d.id != doc_id]

        if len(kb.documents) < original_count:
            kb.updated_at = datetime.now()

            # Delete document file
            kb_docs_dir = self.docs_dir / kb_id
            for file in kb_docs_dir.glob(f"{doc_id}_*"):
                file.unlink()

            self._save_metadata()
            return True
        return False

    async def save_document_content(
        self, kb_id: str, doc_id: str, filename: str, content: bytes
    ) -> Optional[str]:
        """
        Save document content to disk.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier
            filename: Original filename
            content: File content as bytes

        Returns:
            Content hash or None if failed
        """
        if kb_id not in self._knowledge_bases:
            return None

        kb_docs_dir = self.docs_dir / kb_id
        kb_docs_dir.mkdir(parents=True, exist_ok=True)

        file_path = kb_docs_dir / f"{doc_id}_{filename}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        content_hash = hashlib.sha256(content).hexdigest()
        return content_hash

    def get_document_content(
        self, kb_id: str, doc_id: str
    ) -> Optional[bytes]:
        """
        Get document content from disk.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier

        Returns:
            File content as bytes or None if not found
        """
        if kb_id not in self._knowledge_bases:
            return None

        kb_docs_dir = self.docs_dir / kb_id
        files = list(kb_docs_dir.glob(f"{doc_id}_*"))

        if not files:
            return None

        return files[0].read_bytes()

    def get_document_file_path(
        self, kb_id: str, doc_id: str
    ) -> Optional[Path]:
        """
        Get the file path for a document.

        Args:
            kb_id: Knowledge base identifier
            doc_id: Document identifier

        Returns:
            Path object or None if not found
        """
        if kb_id not in self._knowledge_bases:
            return None

        kb_docs_dir = self.docs_dir / kb_id
        files = list(kb_docs_dir.glob(f"{doc_id}_*"))

        if not files:
            return None

        return files[0]

    def set_indexing_strategy(
        self, kb_id: str, strategy: IndexingStrategy
    ) -> bool:
        """
        Set the indexing strategy for a knowledge base.

        Args:
            kb_id: Knowledge base identifier
            strategy: Indexing strategy

        Returns:
            True if updated, False if KB not found
        """
        if kb_id not in self._knowledge_bases:
            return False

        self._knowledge_bases[kb_id].indexing_strategy = strategy
        self._knowledge_bases[kb_id].updated_at = datetime.now()
        self._save_metadata()
        return True

    def update_last_indexed(self, kb_id: str) -> bool:
        """
        Update the last indexed timestamp for a knowledge base.

        Args:
            kb_id: Knowledge base identifier

        Returns:
            True if updated, False if KB not found
        """
        if kb_id not in self._knowledge_bases:
            return False

        self._knowledge_bases[kb_id].last_indexed_at = datetime.now()
        self._save_metadata()
        return True

    def get_stats(self) -> Dict:
        """
        Get overall statistics.

        Returns:
            Dictionary with statistics
        """
        total_docs = sum(len(kb.documents) for kb in self._knowledge_bases.values())
        total_chunks = sum(kb.total_chunks for kb in self._knowledge_bases.values())

        return {
            "total_knowledge_bases": len(self._knowledge_bases),
            "total_documents": total_docs,
            "total_chunks": total_chunks,
        }
