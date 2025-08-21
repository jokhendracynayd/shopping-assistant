"""A small LangGraph-style orchestrator for shopping intents.

This module provides a graph-like interface without requiring the
`langgraph` package so it's easy to run locally. It implements:

- classify_intent(question) -> one of "faq", "order_details", "product_inquiry"
- nodes for each intent
- run_shopping_graph(question) -> dict with {intent, result}

You can later replace the simple functions with actual LangGraph nodes.
"""
from typing import Dict
import re

from app.services.rag_service import answer_shopping_question


def classify_intent(question: str) -> str:
    """Very small keyword-based intent classifier.

Returns: 'faq', 'order_details', or 'product_inquiry'
"""
    q = question.lower()
    # order-related keywords
    if re.search(r"\b(order|status|track|shipping|shipment|deliv)\b", q):
        return "order_details"

    # product inquiry keywords
    if re.search(r"\b(price|cost|spec|specs|dimensions|weight|warranty|feature|model|variant)\b", q):
        return "product_inquiry"

    # fallback to faq
    return "faq"


async def faq_node(question: str) -> Dict:
    # Placeholder FAQ logic: in a real graph we'd query a FAQ DB
    return {"type": "faq", "answer": "(faq) Please check our FAQ page or be more specific."}


async def order_details_node(question: str) -> Dict:
    # Placeholder: extract order id if present
    m = re.search(r"\b(order\s*#?\s*(\w+))\b", question, re.IGNORECASE)
    order_id = m.group(2) if m else None
    if not order_id:
        return {"type": "order_details", "answer": "(order) Please provide your order id."}
    # In real flow we'd query DB / orders service
    return {"type": "order_details", "order_id": order_id, "status": "Processing"}


async def product_inquiry_node(question: str) -> Dict:
    # Use RAG/LLM service to answer product-specific queries
    answer = await answer_shopping_question(question)
    return {"type": "product_inquiry", "answer": answer}


async def run_shopping_graph(question: str) -> Dict:
    """Run the shopping graph: classify intent -> run node -> return structured result."""
    intent = classify_intent(question)
    if intent == "faq":
        result = await faq_node(question)
    elif intent == "order_details":
        result = await order_details_node(question)
    else:
        result = await product_inquiry_node(question)

    return {"intent": intent, "result": result}






# from langgraph.graph import StateGraph, END
# from langgraph.prebuilt import ToolNode
# from langchain.chains import ConversationalRetrievalChain
# from langchain.memory import ConversationBufferMemory
# from langchain_openai import ChatOpenAI

# # Define LLM
# llm = ChatOpenAI(model="gpt-4o")

# # Memory for follow-up handling
# memory = ConversationBufferMemory(return_messages=True)

# # Define retriever (assume db is a Chroma instance)
# retriever = db.as_retriever()

# # Rephrase node: makes follow-up a standalone question
# def rephrase(state):
#     query = state["user_input"]
#     history = memory.chat_memory.messages
#     prompt = f"Rewrite the user query as a standalone question using history:\nHistory:{history}\nQuery:{query}"
#     standalone = llm.predict(prompt)
#     return {"standalone_query": standalone}

# # Retrieval node
# def retrieve(state):
#     docs = retriever.get_relevant_documents(state["standalone_query"])
#     return {"docs": docs}

# # Answer node
# def answer(state):
#     context = "\n".join([d.page_content for d in state["docs"]])
#     query = state["standalone_query"]
#     response = llm.predict(f"Answer based on context:\n{context}\n\nQuestion: {query}")
#     memory.chat_memory.add_user_message(query)
#     memory.chat_memory.add_ai_message(response)
#     return {"answer": response}

# # Build graph
# graph = StateGraph()
# graph.add_node("rephrase", rephrase)
# graph.add_node("retrieve", retrieve)
# graph.add_node("answer", answer)

# graph.set_entry_point("rephrase")
# graph.add_edge("rephrase", "retrieve")
# graph.add_edge("retrieve", "answer")
# graph.add_edge("answer", END)

# app = graph.compile()

# # Run conversation
# state = {"user_input": "What about electronics?"}
# result = app.invoke(state)
# print(result["answer"])

