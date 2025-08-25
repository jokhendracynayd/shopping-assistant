"""LangGraph pipeline for shopping assistant.

Implements a proper stateful graph:
- classify_intent -> sets intent in state
- conditional route by intent
- retrieve_context (for FAQ) -> sets context
- answer (FAQ or Other) -> sets final answer
"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_ollama import OllamaEmbeddings
from langgraph.graph import END
from langgraph.graph import StateGraph

from app.graphs.states import ShoppingState
from app.llm.groq_client import GroqClient
from app.prompts.basic import intent_classification_prompt
from app.prompts.basic import rag_prompt

# Optional retriever integration
from app.retrievers.weaviate_retriever import WeaviateRetriever
from app.utils.logger import get_logger

logger = get_logger("graphs.shopping")


def _init_retriever() -> WeaviateRetriever | None:
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        return WeaviateRetriever(client=None, index_name="FAQ", embedding_fn=embeddings)
    except Exception as e:
        logger.error(f"Retriever initialization failed: {e}")
        return None


parser = JsonOutputParser()
llm_client = GroqClient()
retriever = _init_retriever()


def node_classify(state: ShoppingState) -> dict[str, Any]:
    question = state["question"]
    try:
        chain = intent_classification_prompt | llm_client.llm | parser
        result = chain.invoke({"input": question})
        intent = result.get("intent", "Other")
        return {"intent": intent}
    except Exception as e:
        logger.error("Intent classification failed", extra={"error": str(e)})
        return {"intent": "Other", "error": f"intent_error: {e}"}


def node_retrieve(state: ShoppingState) -> dict[str, Any]:
    question = state["question"]
    if retriever is None:
        return {"context": []}
    try:
        docs = retriever.similarity_search(question, k=5)
        # docs may be list of Document objects or dicts
        texts: list[str] = []
        for d in docs:
            text = getattr(d, "page_content", None) if hasattr(d, "page_content") else None
            if text is None and isinstance(d, dict):
                text = d.get("text") or d.get("content") or d.get("page_content")
            if text:
                texts.append(text)
        return {"context": texts}
    except Exception as e:
        logger.error("Context retrieval failed", extra={"error": str(e)})
        return {"context": [], "error": f"retrieval_error: {e}"}


def node_answer_faq(state: ShoppingState) -> dict[str, Any]:
    question = state["question"]
    context_list = state.get("context") or []
    context_str = "\n\n".join(context_list) if isinstance(context_list, list) else str(context_list)
    try:
        chain = rag_prompt | llm_client.llm
        result = chain.invoke({"question": question, "context": context_str})
        answer = getattr(result, "content", result)
        return {"answer": answer}
    except Exception as e:
        logger.error("Answer generation failed", extra={"error": str(e)})
        return {"answer": "I'm having trouble answering right now.", "error": f"answer_error: {e}"}


def node_answer_other(state: ShoppingState) -> dict[str, Any]:
    return {"answer": "I can only answer product-related FAQs for now."}


def _route_by_intent(state: ShoppingState) -> str:
    intent = (state.get("intent") or "Other").strip()
    if intent.upper() == "FAQ":
        return "retrieve_context"
    return "answer_other"


# Build the graph
graph = StateGraph(ShoppingState)
graph.add_node("classify_intent", node_classify)
graph.add_node("retrieve_context", node_retrieve)
graph.add_node("answer_faq", node_answer_faq)
graph.add_node("answer_other", node_answer_other)

graph.set_entry_point("classify_intent")
graph.add_conditional_edges(
    "classify_intent",
    _route_by_intent,
    {
        "retrieve_context": "retrieve_context",
        "answer_other": "answer_other",
    },
)
graph.add_edge("retrieve_context", "answer_faq")
graph.add_edge("answer_faq", END)
graph.add_edge("answer_other", END)

compiled = graph.compile()


async def run_shopping_graph(question: str) -> dict[str, Any]:
    """Execute the shopping graph end-to-end and return structured result."""
    initial: ShoppingState = {"question": question}
    state: ShoppingState = await compiled.ainvoke(initial)
    return {
        "intent": state.get("intent"),
        "answer": state.get("answer"),
        "context": state.get("context", []),
        "error": state.get("error"),
    }
