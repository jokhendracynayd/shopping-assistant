from fastapi import APIRouter

from app.graphs.shopping_graph import run_shopping_graph
from app.utils.errors import Error, ErrorCode
from app.models.response import Response
from app.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger("api.shopping")

router = APIRouter()


@router.get("/query")
async def query_shopping(q: str):
    """Simple endpoint that answers a shopping question using the RAG service and returns a `Response`."""
    if not q:
        raise Error(ErrorCode.INVALID_INPUT, details={"field": "q"}, message="Query parameter 'q' is required")
    logger.info("handling shopping query", extra={"query": q})
    result = await run_shopping_graph(q)
    return Response(success=True, data=result).dict()
