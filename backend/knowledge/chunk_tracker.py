"""
Chunk tracker for incremental indexing support.

Tracks which document chunks have been indexed using content hashing,
enabling efficient incremental updates when documents change.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Set


class ChunkTracker:
    """
    Tracks indexed document chunks to support incremental indexing.

    Core logic:
    - Computes hash for each chunk (content + doc_id + position)
    - Records all indexed chunk hashes in a persistent file
    - Incremental mode: skips chunks that already exist
    - Full mode: clears all tracked hashes
    """

    def __init__(self, kb_id: str, storage_dir: str = None):
        """
        Initialize chunk tracker for a knowledge base.

        Args:
            kb_id: Knowledge base identifier
            storage_dir: Directory for storing tracker files
        """
        self.kb_id = kb_id
        if storage_dir is None:
            # Default to storage/knowledge under backend
            self.storage_dir = Path(__file__).parent.parent / "storage" / "knowledge"
        else:
            self.storage_dir = Path(storage_dir)

        self.tracker_file = self.storage_dir / f"{kb_id}_chunks.json"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._chunk_hashes: Set[str] = self._load()

    def _load(self) -> Set[str]:
        """Load chunk hashes from file."""
        if self.tracker_file.exists():
            try:
                data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
                return set(data.get("chunk_hashes", []))
            except (json.JSONDecodeError, IOError):
                return set()
        return set()

    def _save(self):
        """Save chunk hashes to file."""
        data = {"chunk_hashes": list(self._chunk_hashes)}
        self.tracker_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def compute_chunk_hash(self, content: str, doc_id: str, chunk_idx: int) -> str:
        """
        Compute unique hash for a chunk.

        Args:
            content: Chunk text content
            doc_id: Document identifier
            chunk_idx: Index of chunk within document

        Returns:
            SHA256 hash string
        """
        data = f"{doc_id}:{chunk_idx}:{content}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def is_chunk_indexed(self, chunk_hash: str) -> bool:
        """Check if a chunk hash is already indexed."""
        return chunk_hash in self._chunk_hashes

    def mark_chunks_indexed(self, chunk_hashes: List[str]):
        """Mark multiple chunks as indexed."""
        self._chunk_hashes.update(chunk_hashes)
        self._save()

    def clear(self):
        """Clear all tracked chunk hashes (before full reindex)."""
        self._chunk_hashes = set()
        self._save()

    def remove_doc_chunks(self, doc_id: str) -> int:
        """
        Remove all chunks belonging to a document.

        Args:
            doc_id: Document identifier to remove

        Returns:
            Number of hashes removed
        """
        original_count = len(self._chunk_hashes)
        self._chunk_hashes = {
            h for h in self._chunk_hashes
            if not h.startswith(f"{doc_id}:")
        }
        self._save()
        return original_count - len(self._chunk_hashes)

    def get_stats(self) -> Dict:
        """Get statistics about tracked chunks."""
        return {
            "total_chunks": len(self._chunk_hashes),
            "kb_id": self.kb_id
        }
