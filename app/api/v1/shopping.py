from fastapi import APIRouter, Body
from typing import List, Dict, Any, Union

from app.graphs.shopping_graph import run_shopping_graph
from app.utils.errors import Error, ErrorCode
from app.models.response import Response
from app.models.payload import QueryPayload
from app.utils.logger import get_logger, setup_logging
from app.services.rag_service import add_documents as rag_add_documents

setup_logging()
logger = get_logger("api.shopping")

router = APIRouter()


class DocumentModel:
    # lightweight runtime-only model (we accept raw dicts from clients)
    def __init__(self, id: str, title: str = "", content: str = ""):
        self.id = id
        self.title = title
        self.content = content


@router.post("/query")
async def query_shopping(payload: QueryPayload):
    """Simple endpoint that answers a shopping question using the RAG service and returns a `Response`.

    Expects JSON body: {"q": "your question"}
    """
    q = payload.q
    if not q:
        raise Error(ErrorCode.INVALID_INPUT, details={"field": "q"}, message="Request body must include 'q' field")
    logger.info("handling shopping query", extra={"query": q})
    result = await run_shopping_graph(q)
    return Response(success=True, data=result)


@router.post("/add-documents")
async def add_documents(payload: Any = Body(...)):
    """Add documents to the retriever.

    Accepts either a JSON object {"documents": [...]} or a bare JSON array [ {...}, ... ].
    """
    # Normalize incoming payload to a list of dicts
    if isinstance(payload, dict) and "documents" in payload:
        docs_raw = payload["documents"]
    elif isinstance(payload, list):
        docs_raw = payload
    else:
        raise Error(ErrorCode.INVALID_INPUT, details={"field": "body"}, message="Expected a JSON array or an object with a 'documents' field")

    if not isinstance(docs_raw, list):
        raise Error(ErrorCode.INVALID_INPUT, details={"field": "documents"}, message="'documents' must be a list")

    docs: List[Dict[str, Any]] = []
    for item in docs_raw:
        if isinstance(item, dict):
            docs.append(item)
        else:
            # Attempt to coerce pydantic-like objects
            try:
                docs.append(item.dict())
            except Exception:
                raise Error(ErrorCode.INVALID_INPUT, details={"item": item}, message="Each document must be a JSON object")

    # Call service to add documents (service should accept list[dict])
    result = await rag_add_documents(docs)
    return Response(success=True, data={"message": result, "count": len(docs)})