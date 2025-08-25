"""Graph state definitions for the shopping assistant LangGraph pipeline.

The state tracks the user question, classified intent, retrieved context and
the final answer. Nodes update subsets of this state as the graph executes.
"""

from __future__ import annotations

from typing import TypedDict


class ShoppingState(TypedDict, total=False):
    """State container for the shopping workflow.

    - question: Raw user query
    - intent: Classified intent label (e.g., "FAQ", "Other")
    - context: Retrieved document snippets used for answering
    - answer: Final answer string
    - error: Optional error message captured during execution
    """

    question: str
    intent: str | None
    context: list[str] | None
    answer: str | None
    error: str | None
