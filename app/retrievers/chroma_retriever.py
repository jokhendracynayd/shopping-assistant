import threading
from collections.abc import Iterable
from collections.abc import Sequence
from typing import Any

from app.retrievers.base import BaseRetriever
from app.retrievers.base import RetrieverConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ChromaRetriever(BaseRetriever):
    """
    Enhanced ChromaDB-based retriever with improved robustness and scalability.
    """

    def __init__(
        self,
        collection_name: str,
        client: Any | None = None,
        embedding_fn: Any | None = None,
        persist_directory: str | None = None,
        config: RetrieverConfig | None = None,
    ) -> None:
        super().__init__(config)

        self.collection_name = collection_name
        self.embedding_fn = embedding_fn
        self.persist_directory = persist_directory
        self._collection = None
        self._lock = threading.RLock()

        self._client = self._initialize_client(client)
        self._collection = self._initialize_collection()

    def _initialize_client(self, client: Any | None) -> Any:
        """Initialize ChromaDB client with error handling."""
        if client is not None:
            return client

        try:
            import chromadb
            from chromadb.config import Settings

            # Configure with persistence if directory provided
            if self.persist_directory:
                settings = Settings(
                    persist_directory=self.persist_directory,
                    anonymized_telemetry=False,
                )
                return chromadb.PersistentClient(path=self.persist_directory, settings=settings)
            return chromadb.EphemeralClient()

        except ImportError as e:
            logger.error("ChromaDB not installed. Install with: pip install chromadb")
            raise ImportError("ChromaDB is required but not installed") from e
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise

    def _initialize_collection(self) -> Any:
        """Initialize ChromaDB collection with version compatibility."""
        try:
            # Try to get existing collection first
            return self._client.get_collection(name=self.collection_name)
        except Exception:
            try:
                # Create new collection
                return self._client.create_collection(name=self.collection_name)
            except Exception:
                try:
                    # Fallback to get_or_create
                    return self._client.get_or_create_collection(name=self.collection_name)
                except Exception as e:
                    logger.error(f"Failed to initialize collection '{self.collection_name}': {e}")
                    raise

    def _add_batch(self, batch: list[dict[str, Any]]) -> None:
        """Add a batch of documents to ChromaDB."""
        if not batch:
            return

        ids = [doc["id"] for doc in batch]
        texts = [doc.get("text", "") for doc in batch]
        metadatas = [doc.get("metadata", {}) for doc in batch]
        embeddings = []

        # Handle embeddings
        for doc in batch:
            emb = doc.get("embedding")
            if emb is None and self.embedding_fn is not None:
                emb = self.embedding_fn(doc.get("text", ""))
            if emb is not None:
                embeddings.append(emb)

        with self._lock:
            kwargs = {
                "ids": ids,
                "documents": texts,
                "metadatas": metadatas,
            }

            # Only include embeddings if we have them for all documents
            if len(embeddings) == len(batch):
                kwargs["embeddings"] = embeddings

            # Try different API methods for version compatibility
            if hasattr(self._collection, "upsert"):
                self._collection.upsert(**kwargs)
            elif hasattr(self._collection, "add"):
                try:
                    self._collection.add(**kwargs)
                except Exception:
                    # If add fails (duplicate IDs), try upsert
                    self._collection.upsert(**kwargs)
            else:
                raise RuntimeError("ChromaDB collection doesn't support add/upsert operations")

    def add_documents(self, documents: Sequence[dict[str, Any]]) -> None:
        """Add documents in batches with error handling."""
        if not documents:
            return

        # Validate documents
        for doc in documents:
            if "id" not in doc:
                raise ValueError("All documents must have an 'id' field")

        self._batch_process(
            list(documents),
            self._add_batch,
            f"Adding documents to ChromaDB collection '{self.collection_name}'",
        )

    def similarity_search(
        self, query: str | Sequence[float], k: int = 4, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Perform similarity search with enhanced error handling."""
        if k <= 0:
            return []

        query_embedding = None
        query_texts = None

        if isinstance(query, str):
            query_texts = [query]
            if self.embedding_fn is not None:
                query_embedding = [self.embedding_fn(query)]
        else:
            query_embedding = [list(query)]

        def _search():
            with self._lock:
                params = {"n_results": k, **kwargs}

                if query_embedding is not None:
                    params["query_embeddings"] = query_embedding
                if query_texts is not None:
                    params["query_texts"] = query_texts

                response = self._collection.query(**params)

                # Process response
                results = []
                ids = response.get("ids", [[]])
                distances = response.get("distances", [[]])
                metadatas = response.get("metadatas", [[]])
                documents = response.get("documents", [[]])

                for i, id_list in enumerate(ids):
                    for j, doc_id in enumerate(id_list):
                        result = {
                            "id": doc_id,
                            "score": 1.0
                            - (
                                distances[i][j]
                                if i < len(distances) and j < len(distances[i])
                                else 0.0
                            ),
                            "metadata": (
                                metadatas[i][j]
                                if i < len(metadatas) and j < len(metadatas[i])
                                else {}
                            ),
                        }
                        if i < len(documents) and j < len(documents[i]):
                            result["text"] = documents[i][j]
                        results.append(result)

                return results

        return self._retry_on_failure(_search)

    def get(self, doc_id: str) -> dict[str, Any] | None:
        """Get document by ID with error handling."""

        def _get():
            with self._lock:
                try:
                    response = self._collection.get(
                        ids=[doc_id], include=["metadatas", "documents"]
                    )

                    ids = response.get("ids", [])
                    metadatas = response.get("metadatas", [])
                    documents = response.get("documents", [])

                    if ids and ids[0]:
                        result = {
                            "id": ids[0],
                            "metadata": metadatas[0] if metadatas else {},
                        }
                        if documents:
                            result["text"] = documents[0]
                        return result

                    return None
                except Exception:
                    # logger.warning(f"Failed to get document {doc_id}: {e}")
                    return None

        return self._retry_on_failure(_get)

    def delete(self, doc_ids: Iterable[str]) -> None:
        """Delete documents by IDs with batch processing."""
        ids_list = list(doc_ids)
        if not ids_list:
            return

        def _delete_batch(batch):
            with self._lock:
                self._collection.delete(ids=batch)

        self._batch_process(
            ids_list,
            _delete_batch,
            f"Deleting documents from ChromaDB collection '{self.collection_name}'",
        )

    def persist(self) -> None:
        """Persist ChromaDB data."""

        def _persist():
            if hasattr(self._client, "persist"):
                self._client.persist()

        self._retry_on_failure(_persist)

    def close(self) -> None:
        """Close ChromaDB connections and cleanup resources."""
        with self._lock:
            if self._closed:
                return

            try:
                if hasattr(self._client, "close"):
                    self._client.close()
            except Exception:
                # logger.warning(f"Error closing ChromaDB client: {e}")
                pass
            finally:
                self._client = None
                self._collection = None
                self._closed = True
