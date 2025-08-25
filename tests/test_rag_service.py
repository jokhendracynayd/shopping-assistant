"""Unit tests for the RAG service."""

from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.services.rag_service import RAGService
from app.services.rag_service import add_documents
from app.services.rag_service import answer_shopping_question


class TestRAGService:
    """Test cases for the RAGService class."""

    @pytest.fixture
    def rag_service(self, mock_llm_client, mock_retriever):
        """Create a RAGService instance with mocked dependencies."""
        service = RAGService()
        service.llm_client = mock_llm_client
        service.retriever = mock_retriever
        return service

    @pytest.mark.asyncio
    async def test_retrieve_context_success(self, rag_service, mock_retriever):
        """Test successful context retrieval."""
        # Test the _retrieve_context method
        contexts = await rag_service._retrieve_context("test question", k=3)

        assert len(contexts) == 2
        assert "test document about product features" in contexts[0]
        assert "pricing information" in contexts[1]
        mock_retriever.similarity_search.assert_called_once_with("test question", k=3)

    @pytest.mark.asyncio
    async def test_retrieve_context_no_retriever(self, rag_service):
        """Test context retrieval when no retriever is available."""
        rag_service.retriever = None

        contexts = await rag_service._retrieve_context("test question")

        assert contexts == []

    @pytest.mark.asyncio
    async def test_retrieve_context_error(self, rag_service, mock_retriever):
        """Test context retrieval with retriever error."""
        mock_retriever.similarity_search.side_effect = Exception("Connection error")

        contexts = await rag_service._retrieve_context("test question")

        assert contexts == []

    def test_format_context_with_documents(self, rag_service):
        """Test context formatting with multiple documents."""
        contexts = ["First document content", "Second document content"]

        formatted = rag_service._format_context(contexts)

        assert "Document 1:\nFirst document content" in formatted
        assert "Document 2:\nSecond document content" in formatted

    def test_format_context_empty(self, rag_service):
        """Test context formatting with no documents."""
        formatted = rag_service._format_context([])

        assert formatted == "No relevant context found."

    @pytest.mark.asyncio
    async def test_generate_answer_success(self, rag_service, mock_llm_client):
        """Test successful answer generation."""
        question = "What are the product features?"
        context = "Document 1:\nAdvanced AI features available"

        answer = await rag_service._generate_answer(question, context)

        assert answer == "Test response from LLM"
        mock_llm_client.llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_answer_error(self, rag_service, mock_llm_client):
        """Test answer generation with LLM error."""
        mock_llm_client.llm.ainvoke.side_effect = Exception("LLM error")

        answer = await rag_service._generate_answer("test", "context")

        assert "technical difficulties" in answer.lower()

    def test_validate_response_valid(self, rag_service):
        """Test response validation with valid response."""
        valid_response = "This is a comprehensive answer with good details about the product."

        is_valid = rag_service._validate_response(valid_response, "test question")

        assert is_valid is True

    def test_validate_response_too_short(self, rag_service):
        """Test response validation with too short response."""
        short_response = "No"

        is_valid = rag_service._validate_response(short_response, "test question")

        assert is_valid is False

    def test_validate_response_generic(self, rag_service):
        """Test response validation with generic response."""
        generic_response = "I don't know"

        is_valid = rag_service._validate_response(generic_response, "test question")

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_answer_shopping_question_success(self, rag_service):
        """Test complete RAG pipeline success."""
        question = "What features does the product have?"

        with (
            patch("app.services.rag_service.get_cached_response", return_value=None),
            patch("app.services.rag_service.cache_response") as mock_cache,
        ):

            answer = await rag_service.answer_shopping_question(question)

            assert answer == "Test response from LLM"
            mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_answer_shopping_question_cached(self, rag_service):
        """Test RAG pipeline with cached response."""
        question = "What features does the product have?"
        cached_answer = "Cached response"

        with patch("app.services.rag_service.get_cached_response", return_value=cached_answer):

            answer = await rag_service.answer_shopping_question(question)

            assert answer == cached_answer

    @pytest.mark.asyncio
    async def test_answer_shopping_question_empty_question(self, rag_service):
        """Test RAG pipeline with empty question."""
        answer = await rag_service.answer_shopping_question("")

        assert "provide a valid question" in answer.lower()

    @pytest.mark.asyncio
    async def test_answer_shopping_question_validation_fail(self, rag_service):
        """Test RAG pipeline when response validation fails."""
        # Mock LLM to return invalid response
        rag_service.llm_client.llm.ainvoke.return_value.content = "No"

        with patch("app.services.rag_service.get_cached_response", return_value=None):

            answer = await rag_service.answer_shopping_question("test question", use_cache=False)

            assert "cannot provide a confident answer" in answer.lower()


class TestRAGServiceFunctions:
    """Test the module-level functions."""

    @pytest.mark.asyncio
    async def test_answer_shopping_question_function(self):
        """Test the main answer_shopping_question function."""
        with patch("app.services.rag_service._rag_service") as mock_service:
            mock_service.answer_shopping_question = AsyncMock(return_value="Test answer")

            result = await answer_shopping_question("Test question")

            assert result == "Test answer"
            mock_service.answer_shopping_question.assert_called_once_with("Test question")

    @pytest.mark.asyncio
    async def test_add_documents_success(self, sample_documents):
        """Test successful document addition."""
        with patch("app.services.rag_service._rag_service") as mock_service:
            mock_service.retriever = Mock()
            mock_service.retriever.add_documents.return_value = None

            result = await add_documents(sample_documents)

            assert "successfully added" in result.lower()
            assert "3 documents" in result
            mock_service.retriever.add_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_documents_empty_list(self):
        """Test document addition with empty list."""
        result = await add_documents([])

        assert result == "No documents provided"

    @pytest.mark.asyncio
    async def test_add_documents_invalid_format(self):
        """Test document addition with invalid document format."""
        invalid_docs = [
            {"id": "doc1"},  # Missing content
            "not a dict",  # Wrong type
            {"text": "content but no id"},  # Missing ID
        ]

        with patch("app.services.rag_service._rag_service") as mock_service:
            mock_service.retriever = Mock()

            result = await add_documents(invalid_docs)

            assert "no valid documents found" in result.lower()

    @pytest.mark.asyncio
    async def test_add_documents_retriever_error(self, sample_documents):
        """Test document addition with retriever error."""
        with patch("app.services.rag_service._rag_service") as mock_service:
            mock_service.retriever = Mock()
            mock_service.retriever.add_documents.side_effect = Exception("Database error")

            result = await add_documents(sample_documents)

            assert "failed to add documents" in result.lower()
            assert "database error" in result.lower()

    @pytest.mark.asyncio
    async def test_add_documents_no_retriever(self, sample_documents):
        """Test document addition when retriever is not available."""
        with patch("app.services.rag_service._rag_service") as mock_service:
            mock_service.retriever = None
            mock_service._initialize_retriever.return_value = None

            result = await add_documents(sample_documents)

            assert "failed to add documents" in result.lower()
