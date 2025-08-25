from typing import Any

from fastapi import APIRouter
from fastapi import Body
from pydantic import ValidationError

from app.graphs.shopping_graph import run_shopping_graph
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
                        "timestamp": "2024-01-15T10:30:00Z"
                    }
                }
            }
        },
        400: {
            "description": "Invalid input or query too long",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "invalid_input",
                            "message": "Query contains potentially harmful content"
                        }
                    }
                }
            }
        },
        413: {
            "description": "Request too large"
        },
        429: {
            "description": "Rate limit exceeded"
        }
    }
)
async def query_shopping(
    payload: QueryPayload = Body(
        ...,
        examples={
            "product_inquiry": {
                "summary": "Product feature inquiry",
                "description": "Ask about specific product features",
                "value": {"q": "What are the features of your latest smartphone?"}
            },
            "general_question": {
                "summary": "General shopping question", 
                "description": "General shopping-related inquiry",
                "value": {"q": "Do you offer free shipping?"}
            },
            "comparison": {
                "summary": "Product comparison",
                "description": "Compare different products",
                "value": {"q": "What's the difference between your Pro and Standard models?"}
            }
        }
    )
):
    """Submit a shopping question and get an AI-powered answer.

    This endpoint processes natural language questions about products, services,
    or shopping-related inquiries using our RAG (Retrieval-Augmented Generation) system.
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
        )

    except ValueError as e:
        logger.warning(f"Document parsing failed: {e}")
        raise Error(ErrorCode.INVALID_INPUT, details={"error": str(e)}, message=str(e))

    except Exception as e:
        logger.error(f"Unexpected error in add_documents: {e}")
        raise Error(
            ErrorCode.INTERNAL_ERROR,
            details={"error": str(e)},
            message="Failed to process documents",
        )
