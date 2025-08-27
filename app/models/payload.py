from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


class QueryPayload(BaseModel):
    """Payload for the shopping query endpoint."""

    q: str = Field(..., title="Question", description="The user's shopping question")
    sessionId: str = Field(..., title="Session ID", description="The user's session ID")
    # context: list[str] = Field(..., title="Context", description="The context for the query")


class DocumentPayload(BaseModel):
    """Individual document for ingestion into the knowledge base."""

    id: str = Field(..., title="Document ID", description="Unique identifier for the document")
    text: str | None = Field(
        None, title="Document Text", description="Main text content of the document"
    )
    content: str | None = Field(
        None, title="Document Content", description="Alternative field for document content"
    )
    title: str | None = Field(
        None, title="Document Title", description="Optional title for the document"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, title="Metadata", description="Additional metadata for the document"
    )

    @field_validator("id")  # type: ignore[misc]
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Document ID cannot be empty")
        return v.strip()

    @field_validator("text", "content", mode="before")  # type: ignore[misc]
    @classmethod
    def validate_content(cls, v: Any) -> str | None:
        if v is not None:
            v = str(v).strip()
            if not v:
                return None
        return v

    def get_text_content(self) -> str:
        """Get the primary text content, preferring 'text' over 'content'."""
        return self.text or self.content or ""

    def has_content(self) -> bool:
        """Check if document has any text content."""
        return bool(self.get_text_content())


class DocumentsPayload(BaseModel):
    """Payload for adding multiple documents to the knowledge base."""

    documents: list[DocumentPayload] = Field(
        ..., title="Documents", description="List of documents to add"
    )

    @field_validator("documents")  # type: ignore[misc]
    @classmethod
    def validate_documents_not_empty(cls, v: list[DocumentPayload]) -> list[DocumentPayload]:
        if not v:
            raise ValueError("Documents list cannot be empty")
        return v


class BulkDocumentPayload(BaseModel):
    """Flexible payload that accepts either wrapped or unwrapped document lists."""

    @classmethod
    def parse_flexible(cls, payload: Any) -> list[DocumentPayload]:
        """Parse flexible document payload formats.

        Accepts:
        - {"documents": [...]} - wrapped format
        - [...] - direct array format
        """
        if isinstance(payload, dict) and "documents" in payload:
            # Wrapped format: {"documents": [...]}
            docs_data = payload["documents"]
        elif isinstance(payload, list):
            # Direct array format: [...]
            docs_data = payload
        else:
            raise ValueError("Expected a JSON array or an object with a 'documents' field")

        if not isinstance(docs_data, list):
            raise ValueError("'documents' must be a list")

        if not docs_data:
            raise ValueError("Documents list cannot be empty")

        # Parse each document
        documents = []
        for i, doc_data in enumerate(docs_data):
            try:
                if isinstance(doc_data, dict):
                    doc = DocumentPayload(**doc_data)
                # Try to convert to dict if it has dict() method
                elif hasattr(doc_data, "dict"):
                    doc = DocumentPayload(**doc_data.dict())
                else:
                    raise ValueError(f"Document {i} must be a JSON object")

                # Validate that document has content
                if not doc.has_content():
                    raise ValueError(f"Document {i} (id: {doc.id}) has no text content")

                documents.append(doc)

            except Exception as e:
                raise ValueError(f"Invalid document at index {i}: {e!s}")

        return documents
