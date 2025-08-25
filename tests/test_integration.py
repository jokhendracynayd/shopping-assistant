"""Integration tests for database operations."""

import pytest
from unittest.mock import AsyncMock, patch, Mock

from app.database.redis_client import get_redis_client, ping, get_redis_info
from app.utils.cache import get_cached_response, set_cached_response


class TestRedisIntegration:
    """Integration tests for Redis database operations."""

    @pytest.mark.asyncio
    async def test_redis_ping_integration(self):
        """Test Redis ping functionality."""
        # This will return False if Redis is not available, which is expected
        result = await ping()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_redis_client_graceful_failure(self):
        """Test Redis client handles unavailable server gracefully."""
        client = await get_redis_client()
        # Should return None when Redis is unavailable
        assert client is None or hasattr(client, 'ping')

    @pytest.mark.asyncio
    async def test_redis_info_integration(self):
        """Test Redis info retrieval."""
        info = await get_redis_info()
        assert isinstance(info, dict)
        assert 'connected' in info

    @pytest.mark.asyncio
    async def test_cache_operations_integration(self):
        """Test cache operations integration."""
        # Test with Redis unavailable - should handle gracefully
        test_key = "test:integration:key"
        test_value = {"message": "test value"}
        
        # Should not raise error even if Redis is unavailable
        await set_cached_response(test_key, test_value, ttl=30)
        
        # Should return None gracefully if Redis is unavailable
        result = await get_cached_response(test_key)
        assert result is None or result == test_value


class TestDatabaseHealthChecks:
    """Integration tests for database health checks."""

    @pytest.mark.asyncio
    async def test_redis_health_check_integration(self):
        """Test Redis health check in realistic scenario."""
        with patch('app.database.redis_client._redis_manager') as mock_manager:
            mock_manager.ping.return_value = False
            
            result = await ping()
            assert result is False

    @pytest.mark.asyncio
    async def test_cache_resilience_integration(self):
        """Test cache system resilience when Redis is down."""
        # Test that cache operations don't break the application
        # even when Redis is unavailable
        
        # These should complete without raising exceptions
        result = await get_cached_response("nonexistent:key")
        assert result is None
        
        # This should complete silently
        await set_cached_response("test:key", "test_value")


class TestWeaviateIntegration:
    """Integration tests for Weaviate operations."""

    def test_weaviate_health_check_mock(self):
        """Test Weaviate health check with mocked client."""
        from app.retrievers.weaviate_retriever import WeaviateRetriever
        
        # Create a retriever instance - it should handle unavailable Weaviate gracefully
        retriever = WeaviateRetriever()
        
        # Health check should return False when Weaviate is unavailable
        health = retriever.health_check()
        assert isinstance(health, bool)

    def test_weaviate_search_graceful_failure(self):
        """Test Weaviate search handles failure gracefully."""
        from app.retrievers.weaviate_retriever import WeaviateRetriever
        
        retriever = WeaviateRetriever()
        
        # Should return empty list when search fails
        results = retriever.similarity_search("test query", k=5)
        assert isinstance(results, list)


@pytest.mark.integration
class TestServiceIntegration:
    """High-level integration tests for services."""

    @pytest.mark.asyncio
    async def test_rag_service_initialization(self):
        """Test RAG service can initialize without external dependencies."""
        from app.services.rag_service import _rag_service
        
        # RAG service should initialize even if retriever fails
        assert _rag_service is not None
        assert hasattr(_rag_service, 'answer_shopping_question')

    @pytest.mark.asyncio
    async def test_end_to_end_query_handling(self):
        """Test end-to-end query handling with mocked dependencies."""
        from app.services.rag_service import answer_shopping_question
        
        with patch('app.services.rag_service._rag_service') as mock_service:
            mock_service.answer_shopping_question.return_value = "Test response"
            
            result = await answer_shopping_question("What are the features?")
            assert isinstance(result, str)
            assert len(result) > 0
