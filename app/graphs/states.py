"""Graph state definitions for the shopping assistant LangGraph pipeline.

The state tracks the user question, classified intent, retrieved context and the final answer. Nodes
update subsets of this state as the graph executes.
"""

from __future__ import annotations

from typing import Any
from typing import TypedDict


class ShoppingState(TypedDict, total=False):
    """Enhanced state container for the shopping workflow.

    Core fields:
    - question: Raw user query
    - intent: Classified intent label (e.g., "FAQ", "Other")
    - context: Retrieved document snippets or formatted context string
    - answer: Final answer string
    - error: Optional error message captured during execution

    Quality and performance fields:
    - confidence: Answer confidence level ("high", "medium", "low", "none")
    - quality_metrics: Detailed quality scoring and validation metrics
    - retrieval_quality: Context retrieval quality ("high", "low", "none", "error")
    - context_count: Number of relevant context documents found
    - validation_failed: Whether answer validation failed
    - validation_reason: Reason for validation failure
    """

    # Core workflow fields
    question: str
    intent: str | None
    context: list[str] | str | None  # Can be list for backward compatibility or formatted string
    answer: str | None
    error: str | None

    # Enhanced quality and performance tracking
    confidence: str | None  # "high", "medium", "low", "none"
    quality_metrics: dict[str, Any] | None  # Detailed quality metrics
    retrieval_quality: str | None  # "high", "low", "none", "error", "no_retriever"
    context_count: int | None  # Number of context documents
    validation_failed: bool | None  # Whether answer validation failed
    validation_reason: str | None  # Reason for validation failure
