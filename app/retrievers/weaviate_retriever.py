from typing import Any, Optional, List, Dict, Iterable, Union, Sequence
import threading
from app.retrievers.base import BaseRetriever, RetrieverConfig
from app.utils.logger import get_logger
from app.config.config import settings
from langchain_weaviate import WeaviateVectorStore
from langchain.schema import Document
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
        client: Optional[Any] = None,
        index_name: str = "default",
        embedding_fn: Optional[Any] = None,
        config: Optional[RetrieverConfig] = None,
    ) -> None:
        super().__init__(config)

        self._client = client
        self.index_name = index_name
        self.embedding_fn = embedding_fn
        self._lock = threading.RLock()
        self.vectorstore = None
        self._client = self._initialize_client(self._client)

    def _initialize_client(self, client: Optional[Any]) -> Any:
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
                embedding=self.embedding_fn,   # ✅ Directly passing embedding class
            )
            print("Vectorstore initialized")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize Weaviate client: {e}")
            raise

    def _add_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Add a batch of documents to Weaviate.

        Each document should be a mapping with at least an `id` and `text` keys.
        """
        if not batch:
            return
        data = []
        with self._lock:
            # print(batch,"@"*20)
            for doc in batch:
                doc_id = doc.get("id")
                if doc_id is None:
                    raise ValueError("All documents must have an 'id' field")

                
                # Primary text property used by the rest of the project is 'text' or 'content'
                text_val = doc.get("text") or doc.get("content") or doc.get("page_content")
                if text_val is None:
                    continue

                # print(text_val,"@"*20)
                met = doc.get("metadata") or {}
                met["id"] = doc_id
                # Convert into Document object
                document = Document(
                    id=doc_id,
                    page_content=text_val,
                    metadata=met,
                )
                data.append(document)
                # print("@"*20)

        try:
            if self.embedding_fn is not None:
                # create with explicit vector
                #TODO: add_documents is not working
                self.vectorstore.add_documents(data)
            
        except Exception:
            pass
        finally:
            self._client.close()

    def add_documents(self, documents: Sequence[Dict[str, Any]]) -> None:
        """Add documents in batches with validation."""
        if not documents:
            return

        # Validate shape
        for doc in documents:
            if not isinstance(doc, dict):
                raise ValueError("Documents must be dictionaries with an 'id' field")
            if "id" not in doc:
                raise ValueError("All documents must have an 'id' field")

        self._batch_process(list(documents), self._add_batch, f"Adding documents to Weaviate '{self.index_name}'")

    def _search(self, query, k):
        with self._lock:
            try:
                results = self.vectorstore.similarity_search(query, k=k)
                return results
            except Exception as e:
                logger.error(f"Weaviate similarity search failed: {e}")
                raise

    
    def similarity_search(self, query: Union[str, Sequence[float]], k: int = 4, **kwargs: Any) -> List[Dict[str, Any]]:
        """Return up to k most similar documents for the query.

        If `query` is text, an `embedding_fn` must be provided or an embedding provider should
        be used externally to produce the vector.
        """
        if k <= 0:
            return []

        # query_vector: Optional[Sequence[float]] = None
        # if isinstance(query, str):
        #     if self.embedding_fn is None:
        #         raise ValueError("embedding_fn required for text queries")
        #     query_vector = self.embedding_fn(query)
        # else:
        #     query_vector = list(query)

        # if query_vector is None:
        #     raise ValueError("Could not generate embedding for query")

        return self._retry_on_failure(self._search, query, k)

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            with self._lock:
                try:
                    obj = self._client.data_object.get(doc_id, class_name=self.index_name)
                    if not obj:
                        return None

                    result: Dict[str, Any] = {
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

        def _delete_batch(batch: List[str]):
            with self._lock:
                for doc_id in batch:
                    try:
                        self._client.data_object.delete(uuid=doc_id, class_name=self.index_name)
                    except Exception as e:
                        logger.warning(f"Failed to delete {doc_id} from Weaviate: {e}")

        self._batch_process(ids_list, _delete_batch, f"Deleting documents from Weaviate '{self.index_name}'")

    def persist(self) -> None:
        # Weaviate persists server-side; nothing local to persist here
        return

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if self._client is not None and hasattr(self._client, "close"):
                    try:
                        self._client.close()
                    except Exception:
                        pass
            finally:
                self._client = None
                self._closed = True


