"""Unit tests for the API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.utils.errors import Error
from app.utils.errors import ErrorCode


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self, client):
        """Test basic health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "uptime_seconds" in data
        assert "version" in data

    def test_liveness_endpoint(self, client):
        """Test liveness probe endpoint."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert "uptime_seconds" in data

    def test_readiness_endpoint_healthy(self, client):
        """Test readiness endpoint when all services are healthy."""
        with (
            patch("app.app.check_rag_service_health") as mock_rag,
            patch("app.app.check_graph_service_health") as mock_graph,
        ):

            mock_rag.return_value = {"service": "rag", "healthy": True}
            mock_graph.return_value = {"service": "graph", "healthy": True}

            response = client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert len(data["services"]) == 2

    def test_readiness_endpoint_unhealthy(self, client):
        """Test readiness endpoint when services are unhealthy."""
        with (
            patch("app.app.check_rag_service_health") as mock_rag,
            patch("app.app.check_graph_service_health") as mock_graph,
        ):

            mock_rag.return_value = {"service": "rag", "healthy": False}
            mock_graph.return_value = {"service": "graph", "healthy": True}

            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"


class TestShoppingEndpoints:
    """Test shopping-related endpoints."""

    def test_query_shopping_success(self, client):
        """Test successful shopping query."""
        with patch("app.api.v1.shopping.run_shopping_graph") as mock_graph:
            mock_graph.return_value = {
                "intent": "FAQ",
                "answer": "The product has advanced AI features.",
                "context": ["Feature documentation"],
            }

            response = client.post(
                "/api/v1/shopping/query", json={"q": "What features does the product have?"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "intent" in data["data"]
            assert "answer" in data["data"]

    def test_query_shopping_empty_question(self, client):
        """Test shopping query with empty question."""
        response = client.post("/api/v1/shopping/query", json={"q": ""})

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "invalid_input"

    def test_query_shopping_missing_question(self, client):
        """Test shopping query with missing question field."""
        response = client.post("/api/v1/shopping/query", json={})

        assert response.status_code == 422  # Pydantic validation error

    def test_add_documents_success(self, client, valid_document_payload):
        """Test successful document addition."""
        with patch("app.api.v1.shopping.rag_add_documents") as mock_add:
            mock_add.return_value = "Successfully added 2 documents to the knowledge base"

            response = client.post("/api/v1/shopping/add-documents", json=valid_document_payload)

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["count"] == 2
            assert "processed_ids" in data["data"]

    def test_add_documents_direct_array(self, client):
        """Test document addition with direct array format."""
        documents = [
            {"id": "doc1", "text": "Document 1 content", "title": "Document 1"},
            {"id": "doc2", "content": "Document 2 content", "title": "Document 2"},
        ]

        with patch("app.api.v1.shopping.rag_add_documents") as mock_add:
            mock_add.return_value = "Successfully added 2 documents"

            response = client.post("/api/v1/shopping/add-documents", json=documents)

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_add_documents_invalid_format(self, client):
        """Test document addition with invalid format."""
        invalid_payload = {"not_documents": ["some", "data"]}

        response = client.post("/api/v1/shopping/add-documents", json=invalid_payload)

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "invalid_input"

    def test_add_documents_missing_id(self, client):
        """Test document addition with missing ID field."""
        invalid_docs = {"documents": [{"text": "Document without ID", "title": "Invalid Document"}]}

        response = client.post("/api/v1/shopping/add-documents", json=invalid_docs)

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_add_documents_missing_content(self, client):
        """Test document addition with missing content."""
        invalid_docs = {"documents": [{"id": "doc1", "title": "Document without content"}]}

        response = client.post("/api/v1/shopping/add-documents", json=invalid_docs)

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False

    def test_add_documents_service_error(self, client, valid_document_payload):
        """Test document addition with service error."""
        with patch("app.api.v1.shopping.rag_add_documents") as mock_add:
            mock_add.side_effect = Exception("Database connection failed")

            response = client.post("/api/v1/shopping/add-documents", json=valid_document_payload)

            assert response.status_code == 500
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "internal_error"


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_api_error_handler(self, client):
        """Test custom API error handler."""
        # This would be triggered by our custom Error() calls
        with patch("app.api.v1.shopping.run_shopping_graph") as mock_graph:
            mock_graph.side_effect = Error(
                ErrorCode.INVALID_INPUT, message="Test error message", details={"field": "test"}
            )

            response = client.post("/api/v1/shopping/query", json={"q": "test question"})

            assert response.status_code == 400
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "invalid_input"
            assert data["error"]["message"] == "Test error message"

    def test_validation_error_handling(self, client):
        """Test Pydantic validation error handling."""
        # Send invalid JSON that doesn't match QueryPayload schema
        response = client.post("/api/v1/shopping/query", json={"wrong_field": "value"})

        assert response.status_code == 422  # Pydantic validation error
        data = response.json()
        assert "detail" in data  # FastAPI default validation error format
