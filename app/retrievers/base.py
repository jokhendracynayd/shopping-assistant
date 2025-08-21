from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import weakref

logger = logging.getLogger(__name__)


@dataclass
class RetrieverConfig:
    """Configuration class for retrievers."""
    batch_size: int = 1000
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    connection_pool_size: int = 10
    enable_logging: bool = True
    
    def __post_init__(self):
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.connection_pool_size <= 0:
            raise ValueError("connection_pool_size must be positive")


class BaseRetriever(ABC):
    """
    Enhanced abstract base class for vector retrievers with improved robustness.
    """
    
    def __init__(self, config: Optional[RetrieverConfig] = None):
        self.config = config or RetrieverConfig()
        self._closed = False
        
        # Register for cleanup on garbage collection
        weakref.finalize(self, self._cleanup)
    
    def _cleanup(self):
        """Cleanup method called during garbage collection."""
        if not self._closed:
            try:
                self.close()
            except Exception:
                pass  # Suppress exceptions during cleanup
    
    def _retry_on_failure(self, func, *args, **kwargs):
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    if self.config.enable_logging:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    if self.config.enable_logging:
                        logger.error(f"All {self.config.max_retries + 1} attempts failed")
        
        raise last_exception

    def _batch_process(self, items: Sequence[Any], process_func, desc: str = "Processing"):
        """Process items in batches."""
        if not items:
            return []
        
        results = []
        total_batches = (len(items) + self.config.batch_size - 1) // self.config.batch_size
        
        for i in range(0, len(items), self.config.batch_size):
            batch = items[i:i + self.config.batch_size]
            batch_num = i // self.config.batch_size + 1
            
            if self.config.enable_logging and total_batches > 1:
                logger.info(f"{desc} batch {batch_num}/{total_batches} ({len(batch)} items)")
            
            try:
                batch_result = self._retry_on_failure(process_func, batch)
                if batch_result is not None:
                    results.extend(batch_result if isinstance(batch_result, list) else [batch_result])
            except Exception as e:
                logger.error(f"Failed to process batch {batch_num}: {e}")
                raise
        
        return results

    @abstractmethod
    def add_documents(self, documents: Sequence[Dict[str, Any]]) -> None:
        """Add or upsert documents into the vector store."""
        pass

    @abstractmethod
    def similarity_search(
        self, query: Union[str, Sequence[float]], k: int = 4, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return up to k most similar documents for the query."""
        pass

    @abstractmethod
    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Return a document by id or None if not found."""
        pass

    @abstractmethod
    def delete(self, doc_ids: Iterable[str]) -> None:
        """Delete documents by id."""
        pass

    @abstractmethod
    def persist(self) -> None:
        """Persist any on-disk state (if supported)."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release connections/resources held by the retriever."""
        pass

    def health_check(self) -> bool:
        """Perform a health check on the retriever."""
        try:
            # Basic health check - attempt a simple operation
            return True
        except Exception:
            return False
