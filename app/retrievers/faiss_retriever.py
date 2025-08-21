from typing import Any, Optional, List, Dict, Iterable, Union, Sequence
import threading
from app.retrievers.base import BaseRetriever, RetrieverConfig
from app.utils.logger import get_logger
import json
from pathlib import Path

logger = get_logger(__name__)


class FaissRetriever(BaseRetriever):
    """
    FAISS-based retriever with persistence and scalability features.
    """

    def __init__(
        self,
        embedding_dim: int,
        index_factory_string: str = "Flat",
        embedding_fn: Optional[Any] = None,
        persist_path: Optional[str] = None,
        normalize_embeddings: bool = True,
        config: Optional[RetrieverConfig] = None,
    ) -> None:
        super().__init__(config)
        
        self.embedding_dim = embedding_dim
        self.index_factory_string = index_factory_string
        self.embedding_fn = embedding_fn
        self.persist_path = persist_path
        self.normalize_embeddings = normalize_embeddings
        
        self._documents = {}  # id -> document mapping
        self._id_to_index = {}  # id -> FAISS index mapping
        self._index_to_id = {}  # FAISS index -> id mapping
        self._lock = threading.RLock()
        
        self._initialize_index()
        self._load_from_disk()

    def _initialize_index(self):
        """Initialize FAISS index."""
        try:
            import faiss
            import numpy as np
            
            self.faiss = faiss
            self.np = np
            
            # Create index based on factory string
            self._index = faiss.index_factory(self.embedding_dim, self.index_factory_string)
            
            # Add ID mapping if not already present
            if not hasattr(self._index, 'id_map'):
                self._index = faiss.IndexIDMap2(self._index)
                
        except ImportError as e:
            logger.error("FAISS not installed. Install with: pip install faiss-cpu or pip install faiss-gpu")
            raise ImportError("FAISS is required but not installed") from e
        except Exception as e:
            logger.error(f"Failed to initialize FAISS index: {e}")
            raise

    def _normalize_embedding(self, embedding: Sequence[float]) -> List[float]:
        """Normalize embedding vector."""
        if not self.normalize_embeddings:
            return list(embedding)
        
        embedding_array = self.np.array(embedding, dtype=self.np.float32)
        norm = self.np.linalg.norm(embedding_array)
        if norm > 0:
            embedding_array = embedding_array / norm
        return embedding_array.tolist()

    def _add_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Add a batch of documents to FAISS index."""
        if not batch:
            return

        embeddings = []
        ids = []
        
        for doc in batch:
            doc_id = doc["id"]
            embedding = doc.get("embedding")
            
            if embedding is None and self.embedding_fn is not None:
                embedding = self.embedding_fn(doc.get("text", ""))
            
            if embedding is None:
                raise ValueError(f"No embedding found for document {doc_id}")
            
            embedding = self._normalize_embedding(embedding)
            embeddings.append(embedding)
            ids.append(hash(doc_id) & 0x7FFFFFFFFFFFFFFF)  # Convert to positive long
            
            # Store document metadata
            self._documents[doc_id] = {
                "id": doc_id,
                "text": doc.get("text", ""),
                "metadata": doc.get("metadata", {}),
            }
            self._id_to_index[doc_id] = len(self._index_to_id)
            self._index_to_id[len(self._index_to_id)] = doc_id

        # Convert to numpy arrays
        embeddings_array = self.np.array(embeddings, dtype=self.np.float32)
        ids_array = self.np.array(ids, dtype=self.np.int64)
        
        with self._lock:
            # Train index if necessary
            if not self._index.is_trained:
                self._index.train(embeddings_array)
            
            # Add embeddings to index
            self._index.add_with_ids(embeddings_array, ids_array)

    def add_documents(self, documents: Sequence[Dict[str, Any]]) -> None:
        """Add documents in batches."""
        if not documents:
            return
            
        # Validate documents
        for doc in documents:
            if "id" not in doc:
                raise ValueError("All documents must have an 'id' field")
        
        self._batch_process(
            list(documents),
            self._add_batch,
            "Adding documents to FAISS index"
        )

    def similarity_search(
        self, query: Union[str, Sequence[float]], k: int = 4, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Perform similarity search using FAISS."""
        if k <= 0:
            return []

        query_embedding = None
        if isinstance(query, str):
            if self.embedding_fn is not None:
                query_embedding = self.embedding_fn(query)
            else:
                raise ValueError("embedding_fn required for text queries")
        else:
            query_embedding = list(query)

        if query_embedding is None:
            raise ValueError("Could not generate embedding for query")

        query_embedding = self._normalize_embedding(query_embedding)

        def _search():
            with self._lock:
                if self._index.ntotal == 0:
                    return []
                
                query_array = self.np.array([query_embedding], dtype=self.np.float32)
                scores, indices = self._index.search(query_array, k)
                
                results = []
                for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                    if idx == -1:  # FAISS returns -1 for empty slots
                        continue
                    
                    # Find document by index
                    doc_id = None
                    for stored_id, stored_idx in self._id_to_index.items():
                        if stored_idx == idx:
                            doc_id = stored_id
                            break
                    
                    if doc_id and doc_id in self._documents:
                        doc = self._documents[doc_id].copy()
                        doc["score"] = float(score) if self.index_factory_string.startswith("Flat") else 1.0 - float(score)
                        results.append(doc)
                
                return results

        return self._retry_on_failure(_search)

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        with self._lock:
            return self._documents.get(doc_id, None)

    def delete(self, doc_ids: Iterable[str]) -> None:
        """Delete documents by IDs (FAISS doesn't support efficient deletion)."""
        # Note: FAISS doesn't support efficient deletion
        # This implementation removes from metadata but not from index
        with self._lock:
            for doc_id in doc_ids:
                if doc_id in self._documents:
                    del self._documents[doc_id]
                if doc_id in self._id_to_index:
                    idx = self._id_to_index[doc_id]
                    del self._id_to_index[doc_id]
                    if idx in self._index_to_id:
                        del self._index_to_id[idx]

    def persist(self) -> None:
        """Persist FAISS index and metadata to disk."""
        if not self.persist_path:
            return

        def _persist():
            with self._lock:
                persist_dir = Path(self.persist_path)
                persist_dir.mkdir(parents=True, exist_ok=True)
                
                # Save FAISS index
                index_path = persist_dir / "index.faiss"
                self.faiss.write_index(self._index, str(index_path))
                
                # Save metadata
                metadata_path = persist_dir / "metadata.json"
                metadata = {
                    "documents": self._documents,
                    "id_to_index": self._id_to_index,
                    "index_to_id": {str(k): v for k, v in self._index_to_id.items()},
                    "embedding_dim": self.embedding_dim,
                    "index_factory_string": self.index_factory_string,
                    "normalize_embeddings": self.normalize_embeddings,
                }
                
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

        self._retry_on_failure(_persist)

    def _load_from_disk(self) -> None:
        """Load FAISS index and metadata from disk."""
        if not self.persist_path or not Path(self.persist_path).exists():
            return

        def _load():
            with self._lock:
                persist_dir = Path(self.persist_path)
                index_path = persist_dir / "index.faiss"
                metadata_path = persist_dir / "metadata.json"
                
                if index_path.exists() and metadata_path.exists():
                    # Load FAISS index
                    self._index = self.faiss.read_index(str(index_path))
                    
                    # Load metadata
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    
                    self._documents = metadata.get("documents", {})
                    self._id_to_index = metadata.get("id_to_index", {})
                    self._index_to_id = {int(k): v for k, v in metadata.get("index_to_id", {}).items()}
                    
                    logger.info(f"Loaded FAISS index with {len(self._documents)} documents")

        try:
            self._retry_on_failure(_load)
        except Exception as e:
            logger.warning(f"Failed to load FAISS index from disk: {e}")

    def close(self) -> None:
        """Close FAISS retriever and cleanup resources."""
        with self._lock:
            if self._closed:
                return
                
            try:
                # Persist before closing
                if self.persist_path:
                    self.persist()
            except Exception as e:
                logger.warning(f"Error persisting FAISS index during close: {e}")
            finally:
                self._index = None
                self._documents.clear()
                self._id_to_index.clear()
                self._index_to_id.clear()
                self._closed = True

    def rebuild_index(self, index_factory_string: Optional[str] = None) -> None:
        """Rebuild the FAISS index with a new factory string."""
        if index_factory_string:
            self.index_factory_string = index_factory_string
        
        with self._lock:
            # Store current documents
            documents = list(self._documents.values())
            
            # Clear current index
            self._initialize_index()
            self._documents.clear()
            self._id_to_index.clear()
            self._index_to_id.clear()
            
            # Re-add all documents
            if documents:
                self.add_documents(documents)

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the FAISS index."""
        with self._lock:
            return {
                "ntotal": self._index.ntotal if self._index else 0,
                "embedding_dim": self.embedding_dim,
                "index_type": self.index_factory_string,
                "is_trained": self._index.is_trained if self._index else False,
                "num_documents": len(self._documents),
                "normalize_embeddings": self.normalize_embeddings,
            }
