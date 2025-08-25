"""A small LangGraph-style orchestrator for shopping intents.

This module provides a graph-like interface without requiring the
`langgraph` package so it's easy to run locally. It implements:

- classify_intent(question) -> one of "faq", "order_details", "product_inquiry"
- nodes for each intent
- run_shopping_graph(question) -> dict with {intent, result}

You can later replace the simple functions with actual LangGraph nodes.
"""
from typing import Dict

from app.services.rag_service import answer_shopping_question
from app.prompts.basic import intent_classification_prompt, rag_prompt
from app.llm.groq_client import GroqClient
from langchain_core.output_parsers import JsonOutputParser
from app.retrievers.weaviate_retriever import WeaviateRetriever
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="nomic-embed-text")
model = GroqClient()
parser = JsonOutputParser()
retriever = WeaviateRetriever(client=None, index_name="FAQ", embedding_fn=embeddings)

def classify_intent(question: str) -> str:
    """Very small keyword-based intent classifier.

    Returns: 'faq', 'order_details', or 'product_inquiry'
    """
    chain = intent_classification_prompt | model.llm | parser
    result = chain.invoke({"input": question})
    return result["intent"]

    # q = question.lower()
    # # order-related keywords
    # if re.search(r"\b(order|status|track|shipping|shipment|deliv)\b", q):
    #     return "order_details"

    # # product inquiry keywords
    # if re.search(r"\b(price|cost|spec|specs|dimensions|weight|warranty|feature|model|variant)\b", q):
    #     return "product_inquiry"

    # # fallback to faq
    # return "faq"


async def faq_node(question: str) -> Dict:
    # Placeholder FAQ logic: in a real graph we'd query a FAQ DB
    # Retrieve top documents, combine their text, then run through the prompt -> llm
    docs = retriever.vectorstore.similarity_search(question, k=5)
    # docs is a list of Document-like objects; extract page_content/text
    chain = rag_prompt | model.llm
    result = chain.invoke({"question": question, "context": docs})
    # result may be a RunnableResult or similar; prefer .content when present
    answer = getattr(result, "content", result)
    return {"type": "faq", "answer": answer}

async def other_query_node(question: str) -> Dict:
    # Placeholder: extract other query details if present
    return {"type": "other", "answer":"I can only answer FAQ questions."}

async def run_shopping_graph(question: str) -> Dict:
    """Run the shopping graph: classify intent -> run node -> return structured result."""
    intent = classify_intent(question)
    if intent == "FAQ":
        result = await faq_node(question)
    else:
        result = await other_query_node(question)

    return {"intent": intent, "result": result}