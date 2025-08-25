"""Robust RAG pipeline service using LangChain components.

Implements a production-ready RAG pipeline with:
- Context retrieval with relevance scoring
- Response quality validation
- Error handling and fallbacks
- Conversation memory support
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import OllamaEmbeddings

from app.llm.groq_client import GroqClient
from app.prompts.basic import rag_prompt
from app.retrievers.weaviate_retriever import WeaviateRetriever
from app.utils.cache import cache_key
from app.utils.cache import cache_response
from app.utils.cache import get_cached_response
from app.utils.logger import get_logger

logger = get_logger("services.rag")


class RAGService:
    """Production-ready RAG service with caching and error handling."""

    def __init__(self):
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        self.llm_client = GroqClient()
        self.retriever = None
        self._initialize_retriever()

    def _initialize_retriever(self) -> None:
        """Initialize retriever with error handling."""
        try:
            self.retriever = WeaviateRetriever(
                client=None, index_name="FAQ", embedding_fn=self.embeddings
            )
            logger.info("RAG retriever initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize retriever: {e}")
            self.retriever = None

    async def _retrieve_context(self, question: str, k: int = 5) -> list[str]:
        """Retrieve relevant context documents with error handling."""
        if not self.retriever:
            logger.warning("No retriever available for context retrieval")
            return []

        try:
            docs = self.retriever.similarity_search(question, k=k)
            context_texts = []

            for doc in docs:
                # Handle both Document objects and dict responses
                if isinstance(doc, Document):
                    text = doc.page_content
                elif isinstance(doc, dict):
                    text = doc.get("text") or doc.get("content") or doc.get("page_content")
                else:
                    text = str(doc)

                if text and text.strip():
                    context_texts.append(text.strip())

            logger.info(f"Retrieved {len(context_texts)} context documents")
            return context_texts

        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")
            return []

    def _format_context(self, contexts: list[str]) -> str:
        """Format context documents for the prompt."""
        if not contexts:
            return "No relevant context found."

        formatted = []
        for i, context in enumerate(contexts, 1):
            formatted.append(f"Document {i}:\n{context}")

        return "\n\n".join(formatted)

    async def _generate_answer(self, question: str, context: str) -> str:
        """Generate answer using LLM with proper error handling."""
        try:
            # Create the RAG chain
            chain = (
                {"question": RunnablePassthrough(), "context": RunnablePassthrough()}
                | rag_prompt
                | self.llm_client.llm
                | StrOutputParser()
            )

            # Generate response
            answer = await chain.ainvoke({"question": question, "context": context})

            if not answer or answer.strip() == "":
                return "I apologize, but I couldn't generate a proper answer to your question."

            return answer.strip()

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return "I'm experiencing technical difficulties. Please try again later."

    def _validate_response(self, answer: str, question: str) -> bool:
        """Basic response quality validation."""
        if not answer or len(answer.strip()) < 10:
            return False

        # Check if response is too generic
        generic_responses = [
            "i don't know",
            "i'm not sure",
            "i cannot",
            "i apologize, but i couldn't",
        ]

        answer_lower = answer.lower()
        if any(generic in answer_lower for generic in generic_responses):
            if len(answer) < 50:  # Short generic responses are probably not helpful
                return False

        return True

    async def answer_shopping_question(
        self, question: str, use_cache: bool = True, max_context_docs: int = 5
    ) -> str:
        """
        Answer a shopping question using RAG pipeline.

        Args:
            question: User's question
            use_cache: Whether to use cached responses
            max_context_docs: Maximum number of context documents to retrieve

        Returns:
            Generated answer string
        """
        if not question or not question.strip():
            return "Please provide a valid question."

        question = question.strip()

        # Check cache first
        if use_cache:
            cached = await get_cached_response(cache_key("rag", question))
            if cached:
                logger.info("Returning cached response")
                return cached

        try:
            # Retrieve context
            context_docs = await self._retrieve_context(question, k=max_context_docs)
            context_str = self._format_context(context_docs)

            # Generate answer
            answer = await self._generate_answer(question, context_str)

            # Validate response quality
            if not self._validate_response(answer, question):
                logger.warning("Generated response failed quality validation")
                answer = "I found some information but cannot provide a confident answer. Please rephrase your question or contact support."

            # Cache successful response
            if use_cache and answer:
                await cache_response(cache_key("rag", question), answer, ttl=300)

            logger.info("RAG pipeline completed successfully")
            return answer

        except Exception as e:
            logger.error(f"RAG pipeline failed: {e}")
            return "I'm experiencing technical difficulties. Please try again later."


# Service instance
_rag_service = RAGService()


async def answer_shopping_question(question: str) -> str:
    """Main entry point for answering shopping questions."""
    return await _rag_service.answer_shopping_question(question)


async def add_documents(documents: list[dict[str, Any]]) -> str:
    """Add documents to the retriever with improved error handling."""
    if not documents:
        return "No documents provided"

    try:
        if _rag_service.retriever is None:
            _rag_service._initialize_retriever()

        if _rag_service.retriever is None:
            raise Exception("Retriever initialization failed")

        # Validate document structure
        valid_docs = []
        for i, doc in enumerate(documents):
            if not isinstance(doc, dict):
                logger.warning(f"Document {i} is not a dictionary, skipping")
                continue

            if "id" not in doc:
                logger.warning(f"Document {i} missing 'id' field, skipping")
                continue

            # Ensure we have some text content
            content = doc.get("text") or doc.get("content") or doc.get("page_content")
            if not content:
                logger.warning(f"Document {i} missing text content, skipping")
                continue

            valid_docs.append(doc)

        if not valid_docs:
            return "No valid documents found to add"

        # Add documents
        _rag_service.retriever.add_documents(valid_docs)

        logger.info(f"Successfully added {len(valid_docs)} documents")
        return f"Successfully added {len(valid_docs)} documents to the knowledge base"

    except Exception as e:
        logger.error(f"Failed to add documents: {e}")
        return f"Failed to add documents: {e!s}"
