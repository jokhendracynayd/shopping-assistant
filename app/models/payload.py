from pydantic import BaseModel, Field


class QueryPayload(BaseModel):
    """Payload for the shopping query endpoint."""
    q: str = Field(..., title="Question", description="The user's shopping question")


