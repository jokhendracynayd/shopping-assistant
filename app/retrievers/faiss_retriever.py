import json
import threading
from collections.abc import Iterable
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.retrievers.base import BaseRetriever
from app.retrievers.base import RetrieverConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FaissRetriever(BaseRetriever):
    """FAISS-based retriever with persistence and scalability features."""

    def __init__(
        self,
        embedding_dim: int,
        index_factory_string: str = "Flat",
        embedding_fn: Any | None = None,
        persist_path: str | None = None,
        normalize_embeddings: bool = True,
        config: RetrieverConfig | None = None,
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
            if not hasattr(self._index, "id_map"):
                self._index = faiss.IndexIDMap2(self._index)

        except ImportError as e:
            logger.error(
                "FAISS not installed. Install with: pip install faiss-cpu or pip install faiss-gpu"
            )
            raise ImportError("FAISS is required but not installed") from e
        except Exception as e:
            logger.error(f"Failed to initialize FAISS index: {e}")
            raise

    def _normalize_embedding(self, embedding: Sequence[float]) -> list[float]:
        """Normalize embedding vector."""
        if not self.normalize_embeddings:
            return list(embedding)

        embedding_array = self.np.array(embedding, dtype=self.np.float32)
        norm = self.np.linalg.norm(embedding_array)
        if norm > 0:
            embedding_array = embedding_array / norm
        return embedding_array.tolist()

    def _add_batch(self, batch: list[dict[str, Any]]) -> None:
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

    def add_documents(self, documents: Sequence[dict[str, Any]]) -> None:
        """Add documents in batches."""
        if not documents:
            return

        # Validate documents
        for doc in documents:
            if "id" not in doc:
                raise ValueError("All documents must have an 'id' field")

        self._batch_process(list(documents), self._add_batch, "Adding documents to FAISS index")

    def similarity_search(
        self, query: str | Sequence[float], k: int = 4, **kwargs: Any
    ) -> list[dict[str, Any]]:
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
                for i, (score, idx) in enumerate(zip(scores[0], indices[0], strict=False)):
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
                        doc["score"] = (
                            float(score)
                            if self.index_factory_string.startswith("Flat")
                            else 1.0 - float(score)
                        )
                        results.append(doc)

                return results

        return self._retry_on_failure(_search)

    def get(self, doc_id: str) -> dict[str, Any] | None:
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

                with open(metadata_path, "w") as f:
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
                    with open(metadata_path) as f:
                        metadata = json.load(f)

                    self._documents = metadata.get("documents", {})
                    self._id_to_index = metadata.get("id_to_index", {})
                    self._index_to_id = {
                        int(k): v for k, v in metadata.get("index_to_id", {}).items()
                    }

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

    def rebuild_index(self, index_factory_string: str | None = None) -> None:
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

    def get_index_stats(self) -> dict[str, Any]:
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


# documents = [
#     {
#         "id": "return_policy_001",
#         "text": "We offer a 30-day return policy for most items in original condition. Some items may be final sale and are not eligible for return.",
#         "metadata": {
#             "category": "Returns & Refunds",
#             "policy_type": "Return Policy",
#             "timeframe_days": 30,
#             "condition_requirements": ["original condition"],
#             "exclusions": ["final sale items"],
#             "last_updated": "2024-01-15"
#         }
#     },
#     {
#         "id": "shipping_intl_002",
#         "text": "Yes, we ship to over 50 countries worldwide. Shipping costs and delivery times vary by destination.",
#         "metadata": {
#             "category": "Shipping & Delivery",
#             "topic": "International Shipping",
#             "countries_served": 50,
#             "cost_calculation": "varies by destination",
#             "service_levels": ["Standard", "Express"]
#         }
#     },
#     {
#         "id": "delivery_time_003",
#         "text": "Delivery times depend on your location and the shipping method chosen. Standard shipping typically takes 3-7 business days.",
#         "metadata": {
#             "category": "Shipping & Delivery",
#             "topic": "Delivery Estimates",
#             "timeframe": "3-7 business days",
#             "factors": ["customer location", "shipping method"],
#             "service_level": "Standard"
#         }
#     },
#     {
#         "id": "payment_methods_004",
#         "text": "We accept all major credit cards (Visa, Mastercard, Amex), PayPal, and Apple Pay.",
#         "metadata": {
#             "category": "Payment",
#             "topic": "Accepted Payment Methods",
#             "methods": ["Visa", "Mastercard", "American Express", "PayPal", "Apple Pay"]
#         }
#     },
#     {
#         "id": "order_tracking_005",
#         "text": "Once your order ships, you'll receive a tracking number via email. You can also check your order status in your account.",
#         "metadata": {
#             "category": "Shipping & Delivery",
#             "topic": "Order Tracking",
#             "notification_method": "email",
#             "tracking_availability": "after shipment",
#             "alternative_method": "online account"
#         }
#     },
#     {
#         "id": "discount_code_issue_006",
#         "text": "Please check the code's spelling, validity period, and if there's a minimum spend requirement. If it still doesn't work, contact our customer support team.",
#         "metadata": {
#             "category": "Discounts & Promotions",
#             "topic": "Troubleshooting Discount Codes",
#             "common_issues": ["spelling errors", "expired code", "minimum spend not met"],
#             "resolution_path": "contact support"
#         }
#     },
#     {
#         "id": "out_of_stock_007",
#         "text": "We restock regularly! Enter your email on the product page for a 'Restock Alert' to be notified when it's available.",
#         "metadata": {
#             "category": "Product Information",
#             "topic": "Out of Stock Items",
#             "action": "restock alert signup",
#             "notification_method": "email",
#             "restock_frequency": "regularly"
#         }
#     },
#     {
#         "id": "change_cancel_order_008",
#         "text": "Please contact us immediately. We can only change or cancel an order if it hasn't yet been processed for shipping.",
#         "metadata": {
#             "category": "Order Management",
#             "topic": "Order Modifications",
#             "action": "contact support",
#             "time_sensitivity": "immediate",
#             "limitation": "before shipping processing"
#         }
#     },
#     {
#         "id": "pricing_transparency_009",
#         "text": "The price you see at checkout is the final price. It includes all applicable taxes and duties for your region.",
#         "metadata": {
#             "category": "Pricing",
#             "topic": "Price Transparency",
#             "included_costs": ["taxes", "duties"],
#             "price_display": "final price at checkout"
#         }
#     },
#     {
#         "id": "account_creation_010",
#         "text": "Click 'Sign In' and then 'Create an Account.' You'll need to provide your name, email, and create a password.",
#         "metadata": {
#             "category": "Account Management",
#             "topic": "Account Creation",
#             "required_fields": ["name", "email", "password"],
#             "process": "self-service"
#         }
#     }
# ]

# faiss_retriever = FaissRetriever(embedding_dim=1536, index_factory_string="Flat", embedding_fn=None, persist_path="faiss_index", normalize_embeddings=True)

# faiss_retriever.add_documents(documents)
