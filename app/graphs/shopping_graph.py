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
    """Classify user intent with fallback to keyword-based classification."""
    question = state["question"]
    
    try:
        # Try LLM-based classification first
        chain = intent_classification_prompt | llm_client.llm | parser
        result = chain.invoke({"input": question})
        intent = result.get("result", "Other")  # Get the intent from the "result" field
        logger.info(f"Intent classification successful: {intent}")
        return {"intent": intent}
    
    except Exception as e:
        error_msg = f"LLM intent classification failed: {type(e).__name__}: {str(e)}"
        logger.warning(error_msg)
        
        # Fallback to simple keyword-based classification
        intent = _classify_intent_fallback(question)
        logger.info(f"Using fallback classification: {intent}")
        return {"intent": intent}


def _classify_intent_fallback(question: str) -> str:
    """Simple keyword-based intent classification as fallback."""
    question_lower = question.lower().strip()
    
    # Greeting patterns
    greeting_words = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "welcome"]
    if any(word in question_lower for word in greeting_words):
        return "Greeting"
    
    # Sales patterns
    sales_words = ["buy", "purchase", "order", "want to", "need", "looking for", "shopping for", "price", "cost", "discount", "deal"]
    if any(word in question_lower for word in sales_words):
        return "Sales"
    
    # Product inquiry patterns
    product_words = ["features", "specifications", "specs", "what is", "how does", "compare", "difference", "about this product"]
    if any(word in question_lower for word in product_words):
        return "Product_Inquiry"
    
    # FAQ patterns
    faq_words = ["policy", "return", "shipping", "warranty", "support", "help", "how to", "when", "where"]
    if any(word in question_lower for word in faq_words):
        return "FAQ"
    
    # Default to Other
    return "Other"


def _filter_relevant_context(question: str, contexts: list[str], min_relevance_threshold: float = 0.3) -> list[str]:
    """Filter contexts based on relevance and quality."""
    if not contexts:
        return []
    
    filtered_contexts = []
    question_lower = question.lower()
    
    for text in contexts:
        if not text or len(text.strip()) < 20:  # Skip very short contexts
            continue
            
        text_lower = text.lower()
        
        # Basic keyword overlap scoring
        question_words = set(question_lower.split())
        text_words = set(text_lower.split())
        overlap = len(question_words.intersection(text_words))
        relevance_score = overlap / len(question_words) if question_words else 0
        
        # Skip contexts with very low relevance
        if relevance_score < min_relevance_threshold:
            continue
            
        # Skip duplicate or very similar contexts
        is_duplicate = False
        for existing in filtered_contexts:
            # Simple duplicate detection based on content similarity
            if len(text) > 50 and text[:50] in existing:
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered_contexts.append(text.strip())
    
    # Limit to top 3 most relevant contexts for better focus
    return filtered_contexts[:3]


def _format_context_with_numbers(contexts: list[str]) -> str:
    """Format contexts for natural conversation (without document numbers)."""
    if not contexts:
        return "No relevant information found."
    
    formatted_contexts = []
    for context in contexts:
        # Clean up the context text
        cleaned_context = context.strip()
        if cleaned_context:
            formatted_contexts.append(cleaned_context)
    
    # Join contexts with clear separation for natural flow
    return "\n\n".join(formatted_contexts) if formatted_contexts else "No relevant information found."


def node_retrieve(state: ShoppingState) -> dict[str, Any]:
    """Enhanced context retrieval with relevance filtering and quality control."""
    question = state["question"]
    if retriever is None:
        logger.warning("No retriever available for context retrieval")
        return {"context": [], "retrieval_quality": "no_retriever"}
    
    try:
        # Retrieve more documents initially for better filtering
        docs = retriever.similarity_search(question, k=8)
        
        # Extract text from documents
        raw_texts: list[str] = []
        for d in docs:
            text = getattr(d, "page_content", None) if hasattr(d, "page_content") else None
            if text is None and isinstance(d, dict):
                text = d.get("text") or d.get("content") or d.get("page_content")
            if text and isinstance(text, str):
                raw_texts.append(text)
        
        # Filter and rank contexts by relevance
        filtered_contexts = _filter_relevant_context(question, raw_texts)
        
        # Format contexts for natural conversation
        formatted_context = _format_context_with_numbers(filtered_contexts)
        
        retrieval_quality = "high" if len(filtered_contexts) >= 2 else "low" if filtered_contexts else "none"
        
        logger.info(f"Retrieved {len(filtered_contexts)} relevant information pieces (quality: {retrieval_quality})")
        
        return {
            "context": formatted_context,
            "retrieval_quality": retrieval_quality,
            "context_count": len(filtered_contexts)
        }
        
    except Exception as e:
        logger.error("Context retrieval failed", extra={"error": str(e)})
        return {"context": "", "error": f"retrieval_error: {e}", "retrieval_quality": "error"}


def _validate_answer_quality(answer: str, question: str, context: str) -> tuple[bool, str, dict[str, Any]]:
    """Validate answer quality for natural conversational responses."""
    if not answer or len(answer.strip()) < 10:
        return False, "Answer too short or empty", {"length": len(answer.strip())}
    
    answer_lower = answer.lower()
    
    # Check for proper refusal phrases (these are GOOD when no context)
    refusal_phrases = [
        "don't have information about",
        "don't have details about", 
        "i don't know",
        "not sure about",
        "don't have that information"
    ]
    
    has_refusal = any(phrase in answer_lower for phrase in refusal_phrases)
    
    # Check for vague/generic responses (potential hallucination)
    vague_phrases = [
        "generally speaking", "typically", "usually", "in most cases",
        "it depends", "may vary", "could be", "might be", "varies depending"
    ]
    
    is_vague = any(phrase in answer_lower for phrase in vague_phrases)
    
    # Check for unnatural formal language (we want conversational tone)
    formal_phrases = [
        "based on the provided", "according to document", "as mentioned in document",
        "the context indicates", "the information states"
    ]
    
    is_formal = any(phrase in answer_lower for phrase in formal_phrases)
    
    # Check for specific, factual content (good signs)
    has_specifics = any([
        any(char.isdigit() for char in answer),  # Contains numbers/specs
        len(answer.split()) > 8,  # Reasonably detailed
        any(word in answer_lower for word in ["can", "will", "offer", "feature", "include"])  # Action words
    ])
    
    # Quality scoring (adjusted for conversational style)
    quality_score = 0
    
    # Positive indicators
    if has_specifics:
        quality_score += 2  # Good specific information
    if has_refusal and ("no relevant" in context.lower() or len(context.strip()) < 50):
        quality_score += 2  # Good to refuse when no/little context
    if not is_vague:
        quality_score += 2  # Not vague
    if not is_formal:
        quality_score += 1  # Natural conversational tone
    if len(answer.strip()) > 30:
        quality_score += 1  # Reasonable length
        
    # Penalty for unwanted patterns
    if is_formal:
        quality_score -= 1  # We don't want formal citations anymore
    
    quality_metrics = {
        "has_refusal": has_refusal,
        "is_vague": is_vague,
        "is_formal": is_formal,
        "has_specifics": has_specifics,
        "quality_score": quality_score,
        "answer_length": len(answer.strip())
    }
    
    # Determine if answer is acceptable (lowered threshold since no citations expected)
    is_valid = quality_score >= 2 or (has_refusal and quality_score >= 1)
    
    validation_reason = ""
    if not is_valid:
        if is_formal:
            validation_reason = "Answer too formal with unwanted citations"
        elif is_vague:
            validation_reason = "Answer too vague or generic"
        elif not has_specifics and not has_refusal:
            validation_reason = "Answer lacks specific information"
    else:
            validation_reason = "Low overall quality score"
    
    return is_valid, validation_reason, quality_metrics


def node_answer_faq(state: ShoppingState) -> dict[str, Any]:
    """Enhanced FAQ answering with quality validation and anti-hallucination measures."""
    question = state["question"]
    context = state.get("context", "")
    retrieval_quality = state.get("retrieval_quality", "unknown")
    context_count = state.get("context_count", 0)
    
    # Handle case where context is still a list (backward compatibility)
    if isinstance(context, list):
        context = _format_context_with_numbers(context)
    
    # Early return if no context available
    if not context or context == "No relevant information found.":
        logger.info("No context available for answering")
        return {
            "answer": "I don't have enough information to answer your question. Please try rephrasing or asking about our specific products.",
            "confidence": "none",
            "quality_metrics": {"no_context": True}
        }
    
    try:
        # Generate answer using enhanced RAG prompt
        chain = rag_prompt | llm_client.llm
        result = chain.invoke({"question": question, "context": context})
        raw_answer = getattr(result, "content", str(result))
        
        if not raw_answer:
            logger.warning("LLM returned empty response")
            return {
                "answer": "I couldn't generate a proper response. Please try rephrasing your question.",
                "confidence": "none",
                "error": "empty_llm_response"
            }
        
        # Validate answer quality and detect hallucination
        is_valid, validation_reason, quality_metrics = _validate_answer_quality(
            raw_answer, question, context
        )
        
        # Determine confidence level
        confidence = "high" if quality_metrics["quality_score"] >= 4 else \
                    "medium" if quality_metrics["quality_score"] >= 3 else \
                    "low"
        
        # Adjust confidence based on retrieval quality
        if retrieval_quality == "low":
            confidence = "low"
        elif retrieval_quality == "none":
            confidence = "none"
        
        # Handle invalid answers
        if not is_valid:
            logger.warning(f"Generated answer failed validation: {validation_reason}")
            fallback_answer = f"I found some information but cannot provide a confident answer about your question. The available information may not be sufficient or directly related to what you're asking about."
            
            return {
                "answer": fallback_answer,
                "confidence": "low",
                "quality_metrics": quality_metrics,
                "validation_failed": True,
                "validation_reason": validation_reason
            }
        
        # Log successful answer generation
        logger.info(f"Generated answer with {confidence} confidence (score: {quality_metrics['quality_score']})")
        
        return {
            "answer": raw_answer.strip(),
            "confidence": confidence,
            "quality_metrics": quality_metrics,
            "context_count": context_count,
            "retrieval_quality": retrieval_quality
        }
        
    except Exception as e:
        logger.error("Answer generation failed", extra={"error": str(e)})
        return {
            "answer": "I'm experiencing technical difficulties while processing your question. Please try again in a moment.",
            "confidence": "none",
            "error": f"answer_error: {e}"
        }


def node_greeting(state: ShoppingState) -> dict[str, Any]:
    """Handle greeting messages with warm, sales-focused responses."""
    from app.prompts.basic import greeting_prompt
    
    question = state["question"]
    
    try:
        chain = greeting_prompt | llm_client.llm
        result = chain.invoke({"question": question})
        answer = getattr(result, "content", str(result))
        
        return {
            "answer": answer.strip(),
            "confidence": "high"
        }
        
    except Exception as e:
        logger.error("Greeting generation failed", extra={"error": str(e)})
        return {
            "answer": "Hello! Welcome to our store! I'm so excited to help you find amazing products today. What can I help you discover?",
            "confidence": "high"
        }


def node_sales(state: ShoppingState) -> dict[str, Any]:
    """Handle sales and purchase intent with enthusiasm."""
    from app.prompts.basic import sales_prompt
    
    question = state["question"]
    
    try:
        # For sales, we can use general product context or work without it
        context = state.get("context", "We have amazing products and great deals available!")
        
        chain = sales_prompt | llm_client.llm
        result = chain.invoke({"question": question, "context": context})
        answer = getattr(result, "content", str(result))
        
        return {
            "answer": answer.strip(),
            "confidence": "high"
        }
        
    except Exception as e:
        logger.error("Sales response generation failed", extra={"error": str(e)})
        return {
            "answer": "I'm so excited to help you find the perfect products! We have incredible deals and top-quality items. What are you looking for today? I'd love to help you find exactly what you need!",
            "confidence": "high"
        }


def node_product_inquiry(state: ShoppingState) -> dict[str, Any]:
    """Handle product-specific questions with detailed information."""
    from app.prompts.basic import product_inquiry_prompt
    
    question = state["question"]
    context = state.get("context", "")
    
    try:
        chain = product_inquiry_prompt | llm_client.llm
        result = chain.invoke({"question": question, "context": context})
        answer = getattr(result, "content", str(result))
        
        return {
            "answer": answer.strip(),
            "confidence": "high" if context else "medium"
        }
        
    except Exception as e:
        logger.error("Product inquiry response failed", extra={"error": str(e)})
        return {
            "answer": "I'd love to help you with that product question! Let me get you the information you need. Could you tell me more about what specific product or feature you're interested in?",
            "confidence": "medium"
        }


def node_answer_other(state: ShoppingState) -> dict[str, Any]:
    """Handle other inquiries with helpful, sales-focused guidance."""
    return {
        "answer": "I'm here to help you with all your shopping needs! I can assist you with finding products, answering questions about features and specifications, helping with purchases, or providing information about our policies. What would you like to know about our amazing products?",
        "confidence": "medium"
    }


def _route_by_intent(state: ShoppingState) -> str:
    """Route to appropriate node based on classified intent."""
    intent = (state.get("intent") or "Other").strip().lower()
    
    # Map intents to their handling strategy
    if intent == "greeting":
        return "greeting"
    elif intent == "sales":
        return "sales"
    elif intent == "product_inquiry":
        return "product_inquiry_with_context"  # Get context first for product questions
    elif intent == "faq":
        return "retrieve_context"  # FAQ needs context retrieval
    else:
        return "answer_other"


# Build the enhanced graph
graph = StateGraph(ShoppingState)

# Add all nodes
graph.add_node("classify_intent", node_classify)
graph.add_node("retrieve_context", node_retrieve)
graph.add_node("greeting", node_greeting)
graph.add_node("sales", node_sales)
graph.add_node("product_inquiry", node_product_inquiry)
graph.add_node("answer_faq", node_answer_faq)
graph.add_node("answer_other", node_answer_other)

# Set entry point
graph.set_entry_point("classify_intent")

# Add conditional routing from intent classification
graph.add_conditional_edges(
    "classify_intent",
    _route_by_intent,
    {
        "greeting": "greeting",
        "sales": "sales",
        "product_inquiry_with_context": "retrieve_context",  # Product questions get context first
        "retrieve_context": "retrieve_context",  # FAQ gets context
        "answer_other": "answer_other",
    },
)

# For context-dependent flows, route based on original intent
def _route_after_context(state: ShoppingState) -> str:
    """Route after context retrieval based on original intent."""
    intent = (state.get("intent") or "Other").strip().lower()
    if intent == "product_inquiry":
        return "product_inquiry"
    else:
        return "answer_faq"  # Default to FAQ handler

graph.add_conditional_edges(
    "retrieve_context",
    _route_after_context,
    {
        "product_inquiry": "product_inquiry",
        "answer_faq": "answer_faq",
    },
)

# Add end edges for all terminal nodes
graph.add_edge("greeting", END)
graph.add_edge("sales", END)
graph.add_edge("product_inquiry", END)
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
