import threading
from collections.abc import Iterable
from collections.abc import Sequence
from typing import Any

from langchain.schema import Document
from langchain_weaviate import WeaviateVectorStore

from app.config.config import settings
from app.retrievers.base import BaseRetriever
from app.retrievers.base import RetrieverConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import weaviate
except Exception:  # pragma: no cover - import error surfaced at runtime
    weaviate = None


class WeaviateRetriever(BaseRetriever):
    """
    Robust Weaviate retriever implementation.

    - Initializes a Weaviate client from settings (cloud if WEAVIATE_URL/WEAVIATE_API_KEY present,
      otherwise falls back to local connection).
    - Accepts an `embedding_fn` callable that converts text -> embedding (list[float]).
    - Provides batch add, similarity search, get, delete, persist, and close methods.
    """

    def __init__(
        self,
        client: Any | None = None,
        index_name: str = "default",
        embedding_fn: Any | None = None,
        config: RetrieverConfig | None = None,
    ) -> None:
        super().__init__(config)

        self._client = client
        self.index_name = index_name
        self.embedding_fn = embedding_fn
        self._lock = threading.RLock()
        self.vectorstore = None
        self._client = self._initialize_client(self._client)

    def _initialize_client(self, client: Any | None) -> Any:
        """Create Weaviate client using settings or provided client."""
        if client is not None:
            return client

        if weaviate is None:
            logger.error("weaviate-client not installed. Install with: pip install weaviate-client")
            raise ImportError("weaviate-client is required but not installed")

        # Prefer cloud connection when settings provided
        try:
            if settings.WEAVIATE_URL and settings.WEAVIATE_API_KEY:
                from weaviate.classes.init import Auth  # local import for optional dependency

                client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=settings.WEAVIATE_URL,
                    auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY),
                )
                print("Cloud client initialized")
            else:
                # Local fallback
                client = weaviate.connect_to_local()
                print("Local client initialized")
            # Initialize the vectorstore with the actual client instance
            self.vectorstore = WeaviateVectorStore(
                client=client,
                index_name=self.index_name,
                text_key="text",
                embedding=self.embedding_fn,  # ✅ Directly passing embedding class
            )
            print("Vectorstore initialized")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize Weaviate client: {e}")
            raise

    def _add_batch(self, batch: list[dict[str, Any]]) -> None:
        """Add a batch of documents to Weaviate with proper error handling and retries.

        Each document should be a mapping with at least an `id` and `text` keys.

        Raises:
            ValueError: If document validation fails
            Exception: If all retry attempts fail
        """
        if not batch:
            logger.debug("Empty batch provided, skipping")
            return

        # Prepare documents with validation
        data = []
        skipped_docs = []

        with self._lock:
            for i, doc in enumerate(batch):
                try:
                    doc_id = doc.get("id")
                    if doc_id is None:
                        raise ValueError(f"Document at index {i} missing required 'id' field")

                    # Primary text property used by the rest of the project is 'text' or 'content'
                    text_val = doc.get("text") or doc.get("content") or doc.get("page_content")
                    if not text_val or not text_val.strip():
                        skipped_docs.append(doc_id)
                        logger.warning(f"Document {doc_id} has no text content, skipping")
                        continue

                    # Prepare metadata
                    metadata = doc.get("metadata", {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    metadata["id"] = doc_id

                    # Add title to metadata if present
                    if doc.get("title"):
                        metadata["title"] = doc.get("title")

                    # Convert into Document object
                    document = Document(
                        id=doc_id,
                        page_content=text_val.strip(),
                        metadata=metadata,
                    )
                    data.append(document)

                except Exception as e:
                    logger.error(f"Failed to prepare document at index {i}: {e}")
                    raise ValueError(f"Document preparation failed at index {i}: {e}")

        if not data:
            logger.warning("No valid documents to add after validation")
            return

        if skipped_docs:
            logger.info(
                f"Skipped {len(skipped_docs)} documents without content: {skipped_docs[:5]}..."
            )

        # Add documents with retry logic
        def _attempt_add_documents():
            if not self.vectorstore:
                raise RuntimeError("Vectorstore not initialized")

            if self.embedding_fn is None:
                raise RuntimeError("Embedding function not available")

            self.vectorstore.add_documents(data)

        try:
            self._retry_on_failure(_attempt_add_documents)
            logger.info(f"Successfully added {len(data)} documents to Weaviate")

        except Exception as e:
            logger.error(f"Failed to add batch of {len(data)} documents after all retries: {e}")
            raise RuntimeError(f"Document ingestion failed: {e}") from e

    def add_documents(self, documents: Sequence[dict[str, Any]]) -> None:
        """Add documents in batches with validation."""
        if not documents:
            return

        # Validate shape
        for doc in documents:
            if not isinstance(doc, dict):
                raise ValueError("Documents must be dictionaries with an 'id' field")
            if "id" not in doc:
                raise ValueError("All documents must have an 'id' field")

        self._batch_process(
            list(documents), self._add_batch, f"Adding documents to Weaviate '{self.index_name}'"
        )

    def _search(self, query, k):
        """Internal search method with connection health check."""
        # Ensure connection is healthy before searching
        self._ensure_connection()

        with self._lock:
            try:
                results = self.vectorstore.similarity_search(query, k=k)
                logger.debug(f"Search returned {len(results)} results")
                return results
            except Exception as e:
                logger.error(f"Weaviate similarity search failed: {e}")
                # Don't retry search failures as they might be query-related
                raise

    def similarity_search(
        self, query: str | Sequence[float], k: int = 4, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Return up to k most similar documents for the query.

        If `query` is text, an `embedding_fn` must be provided or an embedding provider should
        be used externally to produce the vector.
        """
        if k <= 0:
            return []

        return self._retry_on_failure(self._search, query, k)

    def get(self, doc_id: str) -> dict[str, Any] | None:
        def _get():
            with self._lock:
                try:
                    obj = self._client.data_object.get(doc_id, class_name=self.index_name)
                    if not obj:
                        return None

                    result: dict[str, Any] = {
                        "id": obj.get("id") or obj.get("uuid"),
                        "metadata": obj.get("properties", {}).get("metadata", {}),
                    }

                    text = obj.get("properties", {}).get("text")
                    if text:
                        result["text"] = text

                    return result
                except Exception:
                    return None

        return self._retry_on_failure(_get)

    def delete(self, doc_ids: Iterable[str]) -> None:
        ids_list = list(doc_ids)
        if not ids_list:
            return

        def _delete_batch(batch: list[str]):
            with self._lock:
                for doc_id in batch:
                    try:
                        self._client.data_object.delete(uuid=doc_id, class_name=self.index_name)
                    except Exception as e:
                        logger.warning(f"Failed to delete {doc_id} from Weaviate: {e}")

        self._batch_process(
            ids_list, _delete_batch, f"Deleting documents from Weaviate '{self.index_name}'"
        )

    def health_check(self) -> bool:
        """Perform a comprehensive health check on the Weaviate connection."""
        try:
            if self._closed:
                logger.warning("Weaviate client is closed")
                return False

            if not self._client:
                logger.warning("Weaviate client not initialized")
                return False

            if not self.vectorstore:
                logger.warning("Weaviate vectorstore not initialized")
                return False

            # Try a simple operation to verify connectivity
            with self._lock:
                # Attempt to get schema or perform a basic query
                if hasattr(self._client, "is_ready"):
                    ready = self._client.is_ready()
                    if not ready:
                        logger.warning("Weaviate client reports not ready")
                        return False

                # Try a test search with empty query to verify vectorstore works
                try:
                    self.vectorstore.similarity_search("test", k=1)
                    logger.debug("Weaviate health check passed")
                    return True
                except Exception as e:
                    logger.warning(f"Weaviate health check failed during search test: {e}")
                    return False

        except Exception as e:
            logger.error(f"Weaviate health check failed: {e}")
            return False

    def _ensure_connection(self) -> None:
        """Ensure the connection is healthy, reconnect if necessary."""
        if not self.health_check():
            logger.info("Weaviate connection unhealthy, attempting to reconnect...")
            try:
                # Close existing connection
                if self._client:
                    try:
                        self._client.close()
                    except Exception:
                        pass

                # Reinitialize
                self._client = self._initialize_client(None)
                logger.info("Weaviate connection restored")

            except Exception as e:
                logger.error(f"Failed to restore Weaviate connection: {e}")
                raise RuntimeError(f"Weaviate connection could not be restored: {e}")

    def persist(self) -> None:
        # Weaviate persists server-side; nothing local to persist here
        return

    def close(self) -> None:
        """Close the Weaviate client connection safely."""
        with self._lock:
            if self._closed:
                return
            try:
                if self._client is not None and hasattr(self._client, "close"):
                    try:
                        self._client.close()
                        logger.debug("Weaviate client connection closed")
                    except Exception as e:
                        logger.warning(f"Error while closing Weaviate client: {e}")
            finally:
                self._client = None
                self.vectorstore = None
                self._closed = True
