import pytest


@pytest.mark.usefixtures("notify_db_session")
class TestSecurityHeaders:
    """Test security headers for ZAP scan compliance."""

    def test_options_request_returns_204_with_cors_headers(self, client):
        """Test that OPTIONS requests return 204 with proper CORS headers."""
        response = client.options("/")

        assert response.status_code == 204
        assert response.headers.get("Access-Control-Allow-Origin") == "*"
        assert (
            response.headers.get("Access-Control-Allow-Methods")
            == "GET, POST, PUT, DELETE, OPTIONS"
        )
        assert (
            response.headers.get("Access-Control-Allow-Headers")
            == "Content-Type, Authorization"
        )
        assert response.headers.get("Access-Control-Max-Age") == "3600"

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/_status",
            "/_status?simple=1",
            "/_status/live-service-and-organization-counts",
        ],
    )
    def test_status_endpoints_have_cache_control_headers(self, client, endpoint):
        """Test that all status endpoints have proper cache-control headers."""
        response = client.get(endpoint)

        assert response.status_code == 200
        assert (
            response.headers.get("Cache-Control")
            == "no-cache, no-store, must-revalidate"
        )
        assert response.headers.get("Pragma") == "no-cache"
        assert response.headers.get("Expires") == "0"
