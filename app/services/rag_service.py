"""RAG pipeline service stub.

Replace this with LangChain/Chroma integration when ready.
"""

from typing import List, Dict, Any

from app.retrievers.weaviate_retriever import WeaviateRetriever
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")


async def answer_shopping_question(question: str) -> str:
    """Return a placeholder answer for now."""
    return f"(placeholder) I received your question: {question}"


async def add_documents(documents: List[Dict[str, Any]]):
    """Add documents to the retriever."""
    retriever = WeaviateRetriever(client=None, index_name="FAQ", embedding_fn=embeddings)
    retriever.add_documents(documents)
    return "Documents added successfully"