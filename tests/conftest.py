"""Test configuration and fixtures for the shopping assistant application."""

import asyncio
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

from app.llm.groq_client import GroqClient
from app.retrievers.weaviate_retriever import WeaviateRetriever


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    mock_client = Mock(spec=GroqClient)
    mock_client.is_configured.return_value = True
    mock_client.llm = Mock()

    # Mock the chain behavior
    mock_response = Mock()
    mock_response.content = "Test response from LLM"
    mock_client.llm.invoke.return_value = mock_response
    mock_client.llm.ainvoke = AsyncMock(return_value=mock_response)

    return mock_client


@pytest.fixture
def mock_retriever():
    """Mock retriever for testing."""
    mock_retriever = Mock(spec=WeaviateRetriever)
    mock_retriever.health_check.return_value = True

    # Mock search results
    mock_doc1 = Mock()
    mock_doc1.page_content = "This is a test document about product features."
    mock_doc1.metadata = {"id": "doc1", "title": "Product Features"}

    mock_doc2 = Mock()
    mock_doc2.page_content = "This document explains pricing information."
    mock_doc2.metadata = {"id": "doc2", "title": "Pricing"}

    mock_retriever.similarity_search.return_value = [mock_doc1, mock_doc2]
    mock_retriever.add_documents.return_value = None

    return mock_retriever


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    return [
        {
            "id": "doc1",
            "text": "This product has advanced features including AI-powered recommendations.",
            "title": "Product Features",
            "metadata": {"category": "features"},
        },
        {
            "id": "doc2",
            "text": "Our pricing starts at $29.99 per month with a free trial available.",
            "title": "Pricing Information",
            "metadata": {"category": "pricing"},
        },
        {
            "id": "doc3",
            "text": "We offer 24/7 customer support via chat, email, and phone.",
            "title": "Customer Support",
            "metadata": {"category": "support"},
        },
    ]


@pytest.fixture
def sample_questions():
    """Sample questions for testing."""
    return [
        "What features does the product have?",
        "How much does it cost?",
        "Do you provide customer support?",
        "What is the refund policy?",
        "Can I get a demo?",
    ]


@pytest.fixture
def mock_cache_functions():
    """Mock cache functions for testing."""
    cache_storage = {}

    async def mock_get_cached_response(key: str):
        return cache_storage.get(key)

    async def mock_cache_response(key: str, value: str, ttl: int = 300):
        cache_storage[key] = value

    return mock_get_cached_response, mock_cache_response


@pytest.fixture
def valid_document_payload():
    """Valid document payload for API testing."""
    return {
        "documents": [
            {
                "id": "test-doc-1",
                "text": "This is test content for document 1",
                "title": "Test Document 1",
                "metadata": {"category": "test"},
            },
            {
                "id": "test-doc-2",
                "content": "This is test content for document 2",
                "title": "Test Document 2",
            },
        ]
    }


@pytest.fixture
def invalid_document_payload():
    """Invalid document payload for API testing."""
    return {
        "documents": [
            {
                # Missing required 'id' field
                "text": "This document has no ID",
                "title": "Invalid Document",
            },
            {
                "id": "doc-without-content",
                # Missing text/content field
                "title": "Document Without Content",
            },
        ]
    }
