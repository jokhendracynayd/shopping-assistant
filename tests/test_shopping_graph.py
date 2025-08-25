"""Unit tests for the shopping graph service."""

from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.graphs.shopping_graph import _route_by_intent
from app.graphs.shopping_graph import node_answer_faq
from app.graphs.shopping_graph import node_answer_other
from app.graphs.shopping_graph import node_classify
from app.graphs.shopping_graph import node_retrieve
from app.graphs.shopping_graph import run_shopping_graph
from app.graphs.states import ShoppingState


class TestGraphNodes:
    """Test cases for individual graph nodes."""

    def test_node_classify_success(self):
        """Test successful intent classification."""
        state: ShoppingState = {"question": "What are the product features?"}

        with (
            patch("app.graphs.shopping_graph.intent_classification_prompt") as mock_prompt,
            patch("app.graphs.shopping_graph.llm_client") as mock_llm,
            patch("app.graphs.shopping_graph.parser") as mock_parser,
        ):

            # Mock the chain behavior
            mock_chain = Mock()
            mock_chain.invoke.return_value = {"intent": "FAQ"}
            mock_prompt.__or__ = Mock(return_value=mock_chain)

            result = node_classify(state)

            assert result["intent"] == "FAQ"
            assert "error" not in result

    def test_node_classify_error(self):
        """Test intent classification with error."""
        state: ShoppingState = {"question": "Test question"}

        with patch("app.graphs.shopping_graph.intent_classification_prompt") as mock_prompt:
            mock_chain = Mock()
            mock_chain.invoke.side_effect = Exception("Classification error")
            mock_prompt.__or__ = Mock(return_value=mock_chain)

            result = node_classify(state)

            assert result["intent"] == "Other"
            assert "intent_error" in result["error"]

    def test_node_retrieve_success(self):
        """Test successful context retrieval."""
        state: ShoppingState = {"question": "What features are available?"}

        mock_doc1 = Mock()
        mock_doc1.page_content = "Feature 1: Advanced AI"
        mock_doc2 = Mock()
        mock_doc2.page_content = "Feature 2: Real-time analytics"

        with patch("app.graphs.shopping_graph.retriever") as mock_retriever:
            mock_retriever.similarity_search.return_value = [mock_doc1, mock_doc2]

            result = node_retrieve(state)

            assert len(result["context"]) == 2
            assert "Advanced AI" in result["context"][0]
            assert "Real-time analytics" in result["context"][1]

    def test_node_retrieve_no_retriever(self):
        """Test context retrieval when no retriever available."""
        state: ShoppingState = {"question": "Test question"}

        with patch("app.graphs.shopping_graph.retriever", None):
            result = node_retrieve(state)

            assert result["context"] == []

    def test_node_retrieve_error(self):
        """Test context retrieval with error."""
        state: ShoppingState = {"question": "Test question"}

        with patch("app.graphs.shopping_graph.retriever") as mock_retriever:
            mock_retriever.similarity_search.side_effect = Exception("Retrieval error")

            result = node_retrieve(state)

            assert result["context"] == []
            assert "retrieval_error" in result["error"]

    def test_node_answer_faq_success(self):
        """Test successful FAQ answer generation."""
        state: ShoppingState = {
            "question": "What are the features?",
            "context": ["Feature 1: AI-powered", "Feature 2: Real-time"],
        }

        with (
            patch("app.graphs.shopping_graph.rag_prompt") as mock_prompt,
            patch("app.graphs.shopping_graph.llm_client") as mock_llm,
        ):

            mock_chain = Mock()
            mock_response = Mock()
            mock_response.content = "The product features include AI-powered capabilities."
            mock_chain.invoke.return_value = mock_response
            mock_prompt.__or__ = Mock(return_value=mock_chain)

            result = node_answer_faq(state)

            assert result["answer"] == "The product features include AI-powered capabilities."
            assert "error" not in result

    def test_node_answer_faq_no_context(self):
        """Test FAQ answer generation with no context."""
        state: ShoppingState = {"question": "What are the features?", "context": []}

        with (
            patch("app.graphs.shopping_graph.rag_prompt") as mock_prompt,
            patch("app.graphs.shopping_graph.llm_client") as mock_llm,
        ):

            mock_chain = Mock()
            mock_response = Mock()
            mock_response.content = "Based on available information..."
            mock_chain.invoke.return_value = mock_response
            mock_prompt.__or__ = Mock(return_value=mock_chain)

            result = node_answer_faq(state)

            assert "available information" in result["answer"]

    def test_node_answer_faq_error(self):
        """Test FAQ answer generation with error."""
        state: ShoppingState = {"question": "Test question", "context": ["Some context"]}

        with patch("app.graphs.shopping_graph.rag_prompt") as mock_prompt:
            mock_chain = Mock()
            mock_chain.invoke.side_effect = Exception("LLM error")
            mock_prompt.__or__ = Mock(return_value=mock_chain)

            result = node_answer_faq(state)

            assert "trouble answering" in result["answer"]
            assert "answer_error" in result["error"]

    def test_node_answer_other(self):
        """Test other intent answer generation."""
        state: ShoppingState = {"question": "How's the weather?"}

        result = node_answer_other(state)

        assert "FAQ" in result["answer"]
        assert "only answer" in result["answer"]


class TestGraphRouting:
    """Test cases for graph routing logic."""

    def test_route_by_intent_faq(self):
        """Test routing for FAQ intent."""
        state: ShoppingState = {"intent": "FAQ"}

        route = _route_by_intent(state)

        assert route == "retrieve_context"

    def test_route_by_intent_other(self):
        """Test routing for Other intent."""
        state: ShoppingState = {"intent": "Other"}

        route = _route_by_intent(state)

        assert route == "answer_other"

    def test_route_by_intent_unknown(self):
        """Test routing for unknown intent."""
        state: ShoppingState = {"intent": "UNKNOWN_INTENT"}

        route = _route_by_intent(state)

        assert route == "answer_other"

    def test_route_by_intent_missing(self):
        """Test routing when intent is missing."""
        state: ShoppingState = {}

        route = _route_by_intent(state)

        assert route == "answer_other"

    def test_route_by_intent_case_insensitive(self):
        """Test routing is case insensitive."""
        state: ShoppingState = {"intent": "faq"}

        route = _route_by_intent(state)

        assert route == "retrieve_context"


class TestShoppingGraph:
    """Test cases for the complete shopping graph."""

    @pytest.mark.asyncio
    async def test_run_shopping_graph_faq_success(self):
        """Test complete graph execution for FAQ intent."""
        question = "What are the product features?"

        # Mock the compiled graph
        with patch("app.graphs.shopping_graph.compiled") as mock_compiled:
            final_state = {
                "question": question,
                "intent": "FAQ",
                "context": ["Feature 1", "Feature 2"],
                "answer": "The product has advanced features including AI and analytics.",
                "error": None,
            }
            mock_compiled.ainvoke = AsyncMock(return_value=final_state)

            result = await run_shopping_graph(question)

            assert result["intent"] == "FAQ"
            assert (
                result["answer"] == "The product has advanced features including AI and analytics."
            )
            assert result["context"] == ["Feature 1", "Feature 2"]
            assert result["error"] is None

            mock_compiled.ainvoke.assert_called_once()
            call_args = mock_compiled.ainvoke.call_args[0][0]
            assert call_args["question"] == question

    @pytest.mark.asyncio
    async def test_run_shopping_graph_other_intent(self):
        """Test complete graph execution for Other intent."""
        question = "How's the weather today?"

        with patch("app.graphs.shopping_graph.compiled") as mock_compiled:
            final_state = {
                "question": question,
                "intent": "Other",
                "context": [],
                "answer": "I can only answer product-related FAQs for now.",
                "error": None,
            }
            mock_compiled.ainvoke = AsyncMock(return_value=final_state)

            result = await run_shopping_graph(question)

            assert result["intent"] == "Other"
            assert "FAQ" in result["answer"]
            assert result["context"] == []

    @pytest.mark.asyncio
    async def test_run_shopping_graph_with_error(self):
        """Test graph execution with error in state."""
        question = "Test question"

        with patch("app.graphs.shopping_graph.compiled") as mock_compiled:
            final_state = {
                "question": question,
                "intent": "FAQ",
                "context": [],
                "answer": "Error occurred during processing",
                "error": "intent_error: Classification failed",
            }
            mock_compiled.ainvoke = AsyncMock(return_value=final_state)

            result = await run_shopping_graph(question)

            assert result["error"] is not None
            assert "Classification failed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_shopping_graph_exception(self):
        """Test graph execution with exception."""
        question = "Test question"

        with patch("app.graphs.shopping_graph.compiled") as mock_compiled:
            mock_compiled.ainvoke = AsyncMock(side_effect=Exception("Graph execution error"))

            # The function should raise the exception
            with pytest.raises(Exception) as exc_info:
                await run_shopping_graph(question)

            assert "Graph execution error" in str(exc_info.value)


class TestGraphIntegration:
    """Integration tests for graph components."""

    @pytest.mark.asyncio
    async def test_faq_flow_integration(self):
        """Test the complete FAQ flow integration."""
        # Test the flow: classify -> retrieve -> answer
        question = "What features does the product have?"

        # Mock each step
        with (
            patch("app.graphs.shopping_graph.node_classify") as mock_classify,
            patch("app.graphs.shopping_graph.node_retrieve") as mock_retrieve,
            patch("app.graphs.shopping_graph.node_answer_faq") as mock_answer,
        ):

            mock_classify.return_value = {"intent": "FAQ"}
            mock_retrieve.return_value = {"context": ["Feature docs"]}
            mock_answer.return_value = {"answer": "Product has advanced AI features"}

            # Simulate the flow
            state: ShoppingState = {"question": question}

            # Step 1: Classify
            state.update(mock_classify(state))
            assert state["intent"] == "FAQ"

            # Step 2: Route decision
            route = _route_by_intent(state)
            assert route == "retrieve_context"

            # Step 3: Retrieve
            state.update(mock_retrieve(state))
            assert state["context"] == ["Feature docs"]

            # Step 4: Answer
            state.update(mock_answer(state))
            assert "AI features" in state["answer"]

    @pytest.mark.asyncio
    async def test_other_flow_integration(self):
        """Test the complete Other intent flow integration."""
        question = "What's the weather like?"

        with (
            patch("app.graphs.shopping_graph.node_classify") as mock_classify,
            patch("app.graphs.shopping_graph.node_answer_other") as mock_answer,
        ):

            mock_classify.return_value = {"intent": "Other"}
            mock_answer.return_value = {"answer": "I can only answer FAQ questions."}

            # Simulate the flow
            state: ShoppingState = {"question": question}

            # Step 1: Classify
            state.update(mock_classify(state))
            assert state["intent"] == "Other"

            # Step 2: Route decision
            route = _route_by_intent(state)
            assert route == "answer_other"

            # Step 3: Answer directly
            state.update(mock_answer(state))
            assert "FAQ questions" in state["answer"]
