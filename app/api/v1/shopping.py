import asyncio
import json
from typing import Any

from fastapi import APIRouter
from fastapi import Body
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.graphs.shopping_graph import run_shopping_graph
from app.graphs.shopping_graph import run_shopping_graph_stream
from app.models.payload import BulkDocumentPayload
from app.models.payload import QueryPayload
from app.models.response import Response
from app.services.rag_service import add_documents as rag_add_documents
from app.utils.errors import Error
from app.utils.errors import ErrorCode
from app.utils.input_sanitization import sanitize_document_content
from app.utils.input_sanitization import sanitize_llm_query
from app.utils.input_sanitization import validate_document_metadata
from app.utils.logger import get_logger
from app.utils.logger import setup_logging

setup_logging()
logger = get_logger("api.shopping")

router = APIRouter()


@router.post(
    "/query",
    response_model=Response,
    summary="Query the shopping assistant",
    description="Submit a shopping-related question and get an AI-powered answer",
    responses={
        200: {
            "description": "Successful query response",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "data": "Our latest smartphones feature advanced AI cameras, 5G connectivity, and all-day battery life. The flagship model includes a 108MP camera system, 12GB RAM, and 256GB storage.",
                        "message": "Query processed successfully",
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        400: {
            "description": "Invalid input or query too long",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "invalid_input",
                            "message": "Query contains potentially harmful content",
                        }
                    }
                }
            },
        },
        413: {"description": "Request too large"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def query_shopping(
    payload: QueryPayload = Body(
        ...,
        examples={
            "product_inquiry": {
                "summary": "Product feature inquiry",
                "description": "Ask about specific product features",
                "value": {"q": "What are the features of your latest smartphone?"},
            },
            "general_question": {
                "summary": "General shopping question",
                "description": "General shopping-related inquiry",
                "value": {"q": "Do you offer free shipping?"},
            },
            "comparison": {
                "summary": "Product comparison",
                "description": "Compare different products",
                "value": {"q": "What's the difference between your Pro and Standard models?"},
            },
        },
    )
):
    """Submit a shopping question and get an AI-powered answer.

    This endpoint processes natural language questions about products, services, or shopping-related
    inquiries using our RAG (Retrieval-Augmented Generation) system.
    """
    q = payload.q
    if not q:
        raise Error(
            ErrorCode.INVALID_INPUT,
            details={"field": "q"},
            message="Request body must include 'q' field",
        )

    # Sanitize user input
    sanitization_result = sanitize_llm_query(q, strict_mode=True)

    if not sanitization_result.is_safe:
        logger.warning(f"Unsafe query blocked: {sanitization_result.warnings}")
        raise Error(
            ErrorCode.INVALID_INPUT,
            details={
                "field": "q",
                "warnings": sanitization_result.warnings,
                "reason": "Query contains potentially harmful content",
            },
            message="Query contains potentially harmful content and was blocked for security reasons",
        )

    # Log sanitization warnings but allow the query
    if sanitization_result.warnings:
        logger.info(f"Query sanitized with warnings: {sanitization_result.warnings}")

    sanitized_query = sanitization_result.sanitized_text
    logger.info(
        "handling shopping query",
        extra={
            "query": (
                sanitized_query[:100] + "..." if len(sanitized_query) > 100 else sanitized_query
            )
        },
    )

    result = await run_shopping_graph(sanitized_query)
    return Response(success=True, data=result)


@router.post(
    "/query/stream",
    summary="Stream shopping assistant responses",
    description="Submit a shopping-related question and get an AI-powered answer streamed in real-time",
    responses={
        200: {
            "description": "Successful streaming response",
            "content": {
                "text/plain": {
                    "example": 'data: {"chunk_type": "intent", "intent": "FAQ"}\n\ndata: {"chunk_type": "content", "content": "Our return policy..."}\n\n'
                }
            },
        },
        400: {"description": "Invalid input or query too long"},
        413: {"description": "Request too large"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def query_shopping_stream(
    payload: QueryPayload = Body(
        ...,
        examples={
            "product_inquiry": {
                "summary": "Product feature inquiry",
                "description": "Ask about specific product features",
                "value": {"q": "What are the features of your latest smartphone?"},
            },
            "general_question": {
                "summary": "General shopping question",
                "description": "General shopping-related inquiry",
                "value": {"q": "Do you offer free shipping?"},
            },
        },
    )
):
    """Submit a shopping question and get an AI-powered answer streamed in real-time.

    This endpoint processes natural language questions using streaming responses,
    allowing clients to receive partial answers as they're generated.

    The response uses Server-Sent Events (SSE) format with JSON data payloads.
    Each chunk contains a 'chunk_type' field indicating the type of data:
    - 'intent': Classification of the user's question
    - 'metadata': Information about context retrieval and processing
    - 'content': Actual response content (may arrive in multiple chunks)
    - 'final': Final metadata about confidence and quality
    - 'complete': Indicates the response is finished
    - 'error': Error information if something goes wrong
    """
    q = payload.q
    if not q:
        raise Error(
            ErrorCode.INVALID_INPUT,
            details={"field": "q"},
            message="Request body must include 'q' field",
        )

    # Sanitize user input (same as non-streaming)
    sanitization_result = sanitize_llm_query(q, strict_mode=True)

    if not sanitization_result.is_safe:
        logger.warning(f"Unsafe streaming query blocked: {sanitization_result.warnings}")
        raise Error(
            ErrorCode.INVALID_INPUT,
            details={
                "field": "q",
                "warnings": sanitization_result.warnings,
                "reason": "Query contains potentially harmful content",
            },
            message="Query contains potentially harmful content and was blocked for security reasons",
        )

    # Log sanitization warnings but allow the query
    if sanitization_result.warnings:
        logger.info(f"Streaming query sanitized with warnings: {sanitization_result.warnings}")

    sanitized_query = sanitization_result.sanitized_text
    logger.info(
        "handling streaming shopping query",
        extra={
            "query": (
                sanitized_query[:100] + "..." if len(sanitized_query) > 100 else sanitized_query
            )
        },
    )

    async def stream_generator():
        """Generate SSE-formatted streaming response."""
        try:
            async for chunk in run_shopping_graph_stream(sanitized_query):
                # Format as Server-Sent Events
                chunk_json = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {chunk_json}\n\n"

                # Add small delay to prevent overwhelming the client
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.exception("Error in streaming response")
            # Send error chunk
            error_chunk = {
                "chunk_type": "error",
                "error": str(e),
                "fallback": "I'm experiencing technical difficulties. Please try your question again.",
            }
            error_json = json.dumps(error_chunk, ensure_ascii=False)
            yield f"data: {error_json}\n\n"
        finally:
            # Always send a final end-of-stream marker
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/add-documents")
async def add_documents(payload: Any = Body(...)):
    """Add documents to the retriever with proper validation.

    Accepts either:
    - JSON object: {"documents": [{"id": "1", "text": "content"}, ...]}
    - JSON array: [{"id": "1", "text": "content"}, ...]

    Each document must have:
    - id: Unique identifier (required)
    - text or content: Document content (at least one required)
    - title: Optional title
    - metadata: Optional additional metadata
    """
    try:
        # Parse and validate documents using our flexible parser
        documents = BulkDocumentPayload.parse_flexible(payload)

        logger.info(f"Validated {len(documents)} documents for ingestion")

        # Convert Pydantic models to dictionaries for the service with sanitization
        docs_for_service = []
        sanitization_warnings = []

        for doc in documents:
            # Sanitize document content
            content = doc.get_text_content()
            content_result = sanitize_document_content(content)

            if content_result.warnings:
                sanitization_warnings.extend(
                    [f"Document {doc.id}: {w}" for w in content_result.warnings]
                )

            # Sanitize metadata
            sanitized_metadata, metadata_warnings = validate_document_metadata(doc.metadata or {})
            if metadata_warnings:
                sanitization_warnings.extend(
                    [f"Document {doc.id} metadata: {w}" for w in metadata_warnings]
                )

            doc_dict = {
                "id": doc.id,
                "text": content_result.sanitized_text,
                "metadata": sanitized_metadata,
            }

            # Add optional fields if present (also sanitize title)
            if doc.title:
                title_result = sanitize_document_content(doc.title)
                doc_dict["title"] = title_result.sanitized_text
                doc_dict["metadata"]["title"] = title_result.sanitized_text
                if title_result.warnings:
                    sanitization_warnings.extend(
                        [f"Document {doc.id} title: {w}" for w in title_result.warnings]
                    )

            docs_for_service.append(doc_dict)

        # Log sanitization warnings
        if sanitization_warnings:
            logger.info(
                f"Document sanitization warnings: {sanitization_warnings[:10]}"
            )  # Log first 10

        # Call service to add documents
        result = await rag_add_documents(docs_for_service)

        logger.info(f"Successfully processed {len(documents)} documents")
        return Response(
            success=True,
            data={
                "message": result,
                "count": len(documents),
                "processed_ids": [doc.id for doc in documents],
            },
        )

    except ValidationError as e:
        logger.warning(f"Document validation failed: {e}")
        raise Error(
            ErrorCode.INVALID_INPUT,
            details={"validation_errors": e.errors()},
            message="Document validation failed",
        ) from e

    except ValueError as e:
        logger.warning(f"Document parsing failed: {e}")
        raise Error(ErrorCode.INVALID_INPUT, details={"error": str(e)}, message=str(e)) from e

    except Exception as e:
        logger.exception("Unexpected error in add_documents")
        raise Error(
            ErrorCode.INTERNAL_ERROR,
            details={"error": str(e)},
            message="Failed to process documents",
        ) from e
