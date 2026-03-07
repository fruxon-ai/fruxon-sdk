"""Tests for the fruxon API client."""

import io
import json
import urllib.error
import urllib.request

import pytest

from fruxon.exceptions import (
    AuthenticationError,
    ForbiddenError,
    FruxonAPIError,
    FruxonConnectionError,
    NotFoundError,
    ValidationError,
)
from fruxon.fruxon import (
    ExecutionResult,
    ExecutionTrace,
    FruxonClient,
    _parse_execution_result,
)

SAMPLE_RESPONSE = {
    "response": "Here is your answer.",
    "trace": {
        "agentId": "agent-1",
        "agentRevision": 3,
        "createdAt": 1700000000,
        "parameters": {},
        "startTime": 1700000000,
        "endTime": 1700000005,
        "duration": 5000,
        "traces": [],
        "result": {"strValue": "Here is your answer."},
        "inputCost": 0.001,
        "outputCost": 0.002,
        "totalCost": 0.003,
    },
    "sessionId": "sess-abc",
    "links": [],
    "executionRecordId": "rec-123",
}


class _MockResponse:
    """Mock urllib response with context manager support."""

    def __init__(self, data: dict):
        self._data = json.dumps(data).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def client():
    return FruxonClient(api_key="test-key", tenant="test-tenant")


class TestFruxonClientInit:
    def test_stores_config(self):
        c = FruxonClient(api_key="k", tenant="t")
        assert c._api_key == "k"
        assert c._tenant == "t"
        assert c._base_url == "https://api.fruxon.com"
        assert c._timeout == 120.0

    def test_custom_base_url(self):
        c = FruxonClient(api_key="k", tenant="t", base_url="https://staging.fruxon.com/")
        assert c._base_url == "https://staging.fruxon.com"

    def test_custom_timeout(self):
        c = FruxonClient(api_key="k", tenant="t", timeout=30.0)
        assert c._timeout == 30.0


class TestFruxonClientExecute:
    def test_sends_correct_request(self, client, monkeypatch):
        """Verify URL, headers, and body are correctly constructed."""
        captured = {}

        def mock_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["method"] = req.method
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _MockResponse(SAMPLE_RESPONSE)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        client.execute("my-agent", parameters={"q": "hello"}, session_id="sess-1")

        assert captured["url"] == "https://api.fruxon.com/v1/tenants/test-tenant/agents/my-agent:execute"
        assert captured["method"] == "POST"
        assert captured["headers"]["Content-type"] == "application/json"
        assert captured["headers"]["X-api-key"] == "test-key"
        assert captured["body"] == {"parameters": {"q": "hello"}, "sessionId": "sess-1"}
        assert captured["timeout"] == 120.0

    def test_omits_none_fields(self, client, monkeypatch):
        """Only non-None fields appear in the request body."""
        captured = {}

        def mock_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _MockResponse(SAMPLE_RESPONSE)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        client.execute("my-agent")
        assert captured["body"] == {}

    def test_maps_chat_user(self, client, monkeypatch):
        captured = {}

        def mock_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _MockResponse(SAMPLE_RESPONSE)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        client.execute("my-agent", chat_user={"id": "user-1", "name": "Alice"})
        assert captured["body"]["chatUser"] == {"id": "user-1", "name": "Alice"}

    def test_returns_execution_result(self, client, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _MockResponse(SAMPLE_RESPONSE))

        result = client.execute("my-agent")

        assert isinstance(result, ExecutionResult)
        assert result.response == "Here is your answer."
        assert result.session_id == "sess-abc"
        assert result.execution_record_id == "rec-123"
        assert isinstance(result.trace, ExecutionTrace)
        assert result.trace.agent_id == "agent-1"
        assert result.trace.agent_revision == 3
        assert result.trace.duration == 5000
        assert result.trace.input_cost == 0.001
        assert result.trace.output_cost == 0.002
        assert result.trace.total_cost == 0.003


class TestErrorHandling:
    def _make_http_error(self, status: int, body: dict | None = None):
        if body is None:
            body = {"title": "Test Error", "detail": "Something went wrong"}
        return urllib.error.HTTPError(
            url="https://api.fruxon.com/v1/test",
            code=status,
            msg="Error",
            hdrs=None,
            fp=io.BytesIO(json.dumps(body).encode("utf-8")),
        )

    def test_401_raises_authentication_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(401)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(AuthenticationError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 401

    def test_403_raises_forbidden_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(403)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(ForbiddenError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 403

    def test_404_raises_not_found_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(404)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(NotFoundError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 404

    def test_400_raises_validation_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(400)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(ValidationError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 400

    def test_422_raises_validation_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(422)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(ValidationError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 422

    def test_unknown_status_raises_api_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise self._make_http_error(500)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(FruxonAPIError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 500

    def test_malformed_error_body(self, client, monkeypatch):
        """Non-JSON error response falls back gracefully."""
        error = urllib.error.HTTPError(
            url="https://api.fruxon.com/v1/test",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=io.BytesIO(b"<html>Bad Gateway</html>"),
        )

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(error))

        with pytest.raises(FruxonAPIError) as exc_info:
            client.execute("my-agent")
        assert exc_info.value.status == 502
        assert exc_info.value.title == "Error"

    def test_network_error_raises_connection_error(self, client, monkeypatch):
        def mock_urlopen(req, timeout=None):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with pytest.raises(FruxonConnectionError, match="Connection refused"):
            client.execute("my-agent")


class TestParseResult:
    def test_full_response(self):
        result = _parse_execution_result(SAMPLE_RESPONSE)
        assert result.response == "Here is your answer."
        assert result.session_id == "sess-abc"
        assert result.execution_record_id == "rec-123"
        assert result.trace.agent_id == "agent-1"
        assert result.trace.duration == 5000
        assert result.trace.total_cost == 0.003

    def test_missing_fields_default(self):
        result = _parse_execution_result({})
        assert result.response == ""
        assert result.session_id == ""
        assert result.execution_record_id == ""
        assert result.trace.agent_id == ""
        assert result.trace.duration == 0
        assert result.trace.total_cost == 0.0
