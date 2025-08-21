from typing import Any, Optional, List, Dict, Iterable, Union, Sequence
import threading
from app.retrievers.base import BaseRetriever, RetrieverConfig
from app.utils.logger import get_logger
from contextlib import contextmanager
import json

logger = get_logger(__name__)


class PgVectorRetriever(BaseRetriever):
    """
    PostgreSQL with pgvector extension retriever implementation.
    """

    def __init__(
        self,
        connection_string: str,
        table_name: str,
        embedding_column: str = "embedding",
        text_column: str = "text",
        metadata_column: str = "metadata",
        id_column: str = "id",
        embedding_dim: int = 1536,
        embedding_fn: Optional[Any] = None,
        config: Optional[RetrieverConfig] = None,
    ) -> None:
        super().__init__(config)
        
        self.connection_string = connection_string
        self.table_name = table_name
        self.embedding_column = embedding_column
        self.text_column = text_column
        self.metadata_column = metadata_column
        self.id_column = id_column
        self.embedding_dim = embedding_dim
        self.embedding_fn = embedding_fn
        self._pool = None
        self._lock = threading.RLock()
        
        self._initialize_pool()
        self._ensure_table_exists()

    def _initialize_pool(self):
        """Initialize connection pool."""
        try:
            import psycopg2
            from psycopg2 import pool
            
            self._pool = pool.ThreadedConnectionPool(
                1, self.config.connection_pool_size,
                self.connection_string,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        except ImportError as e:
            logger.error("psycopg2 not installed. Install with: pip install psycopg2-binary")
            raise ImportError("psycopg2 is required but not installed") from e
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    @contextmanager
    def _get_connection(self):
        """Get database connection from pool."""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)

    def _ensure_table_exists(self):
        """Create table and indexes if they don't exist."""
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.id_column} TEXT PRIMARY KEY,
            {self.text_column} TEXT,
            {self.metadata_column} JSONB,
            {self.embedding_column} vector({self.embedding_dim})
        );
        
        CREATE INDEX IF NOT EXISTS {self.table_name}_{self.embedding_column}_idx 
        ON {self.table_name} USING ivfflat ({self.embedding_column} vector_cosine_ops)
        WITH (lists = 100);
        """
        
        def _create():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Enable pgvector extension
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(create_table_sql)
                    conn.commit()
        
        self._retry_on_failure(_create)

    def _add_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Add a batch of documents to PostgreSQL."""
        if not batch:
            return

        def _insert_batch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    values = []
                    for doc in batch:
                        doc_id = doc["id"]
                        text = doc.get("text", "")
                        metadata = json.dumps(doc.get("metadata", {}))
                        
                        embedding = doc.get("embedding")
                        if embedding is None and self.embedding_fn is not None:
                            embedding = self.embedding_fn(text)
                        
                        if embedding is None:
                            raise ValueError(f"No embedding found for document {doc_id}")
                        
                        values.append((doc_id, text, metadata, embedding))
                    
                    # Use ON CONFLICT for upsert behavior
                    insert_sql = f"""
                    INSERT INTO {self.table_name} 
                    ({self.id_column}, {self.text_column}, {self.metadata_column}, {self.embedding_column})
                    VALUES %s
                    ON CONFLICT ({self.id_column}) DO UPDATE SET
                        {self.text_column} = EXCLUDED.{self.text_column},
                        {self.metadata_column} = EXCLUDED.{self.metadata_column},
                        {self.embedding_column} = EXCLUDED.{self.embedding_column};
                    """
                    
                    import psycopg2.extras
                    psycopg2.extras.execute_values(
                        cur, insert_sql, values, template=None, page_size=1000
                    )
                    conn.commit()

        self._retry_on_failure(_insert_batch)

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
            f"Adding documents to pgVector table '{self.table_name}'"
        )

    def similarity_search(
        self, query: Union[str, Sequence[float]], k: int = 4, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Perform similarity search using pgvector."""
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

        def _search():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    search_sql = f"""
                    SELECT {self.id_column}, {self.text_column}, {self.metadata_column},
                           1 - ({self.embedding_column} <=> %s) as score
                    FROM {self.table_name}
                    ORDER BY {self.embedding_column} <=> %s
                    LIMIT %s;
                    """
                    
                    cur.execute(search_sql, (query_embedding, query_embedding, k))
                    rows = cur.fetchall()
                    
                    results = []
                    for row in rows:
                        result = {
                            "id": row[self.id_column],
                            "score": float(row["score"]),
                            "metadata": row[self.metadata_column] or {},
                        }
                        if row[self.text_column]:
                            result["text"] = row[self.text_column]
                        results.append(result)
                    
                    return results

        return self._retry_on_failure(_search)

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        def _get():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    select_sql = f"""
                    SELECT {self.id_column}, {self.text_column}, {self.metadata_column}
                    FROM {self.table_name}
                    WHERE {self.id_column} = %s;
                    """
                    
                    cur.execute(select_sql, (doc_id,))
                    row = cur.fetchone()
                    
                    if row:
                        result = {
                            "id": row[self.id_column],
                            "metadata": row[self.metadata_column] or {},
                        }
                        if row[self.text_column]:
                            result["text"] = row[self.text_column]
                        return result
                    
                    return None

        return self._retry_on_failure(_get)

    def delete(self, doc_ids: Iterable[str]) -> None:
        """Delete documents by IDs."""
        ids_list = list(doc_ids)
        if not ids_list:
            return

        def _delete_batch(batch):
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    delete_sql = f"DELETE FROM {self.table_name} WHERE {self.id_column} = ANY(%s);"
                    cur.execute(delete_sql, (batch,))
                    conn.commit()

        self._batch_process(
            ids_list,
            _delete_batch,
            f"Deleting documents from pgVector table '{self.table_name}'"
        )

    def persist(self) -> None:
        """PostgreSQL automatically persists data."""
        pass

    def close(self) -> None:
        """Close connection pool."""
        with self._lock:
            if self._closed:
                return
                
            try:
                if self._pool:
                    self._pool.closeall()
            except Exception as e:
                logger.warning(f"Error closing pgVector connection pool: {e}")
            finally:
                self._pool = None
                self._closed = True
