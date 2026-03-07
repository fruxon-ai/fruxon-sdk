"""Fruxon API client for executing agents on the Fruxon platform."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from fruxon.exceptions import (
    AuthenticationError,
    ForbiddenError,
    FruxonAPIError,
    FruxonConnectionError,
    NotFoundError,
    ValidationError,
)

_STATUS_EXCEPTIONS: dict[int, type[FruxonAPIError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    422: ValidationError,
}


@dataclass(frozen=True)
class ExecutionTrace:
    """Execution trace metadata."""

    agent_id: str
    agent_revision: int
    duration: int
    input_cost: float
    output_cost: float
    total_cost: float


@dataclass(frozen=True)
class ExecutionResult:
    """Result of an agent execution."""

    response: str
    trace: ExecutionTrace
    session_id: str
    links: list[dict[str, object]]
    execution_record_id: str


class FruxonClient:
    """Client for the Fruxon platform API."""

    DEFAULT_BASE_URL = "https://api.fruxon.com"

    def __init__(
        self,
        *,
        api_key: str,
        tenant: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._tenant = tenant
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def execute(
        self,
        agent: str,
        *,
        parameters: dict[str, object] | None = None,
        attachments: list[dict[str, object]] | None = None,
        chat_user: dict[str, object] | None = None,
        session_id: str | None = None,
    ) -> ExecutionResult:
        """Execute an agent and return the result.

        Args:
            agent: The agent identifier.
            parameters: Execution parameters and inputs.
            attachments: File attachments.
            chat_user: Chat user information.
            session_id: Session identifier for multi-turn conversations.
        """
        url = f"{self._base_url}/v1/tenants/{self._tenant}/agents/{agent}:execute"

        body: dict[str, object] = {}
        if parameters is not None:
            body["parameters"] = parameters
        if attachments is not None:
            body["attachments"] = attachments
        if chat_user is not None:
            body["chatUser"] = chat_user
        if session_id is not None:
            body["sessionId"] = session_id

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": self._api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            _raise_api_error(e)
        except urllib.error.URLError as e:
            raise FruxonConnectionError(str(e.reason)) from e

        return _parse_execution_result(result)


def _raise_api_error(error: urllib.error.HTTPError) -> None:
    """Parse an HTTP error response and raise the appropriate exception."""
    try:
        body = json.loads(error.read().decode("utf-8"))
        title = body.get("title", "Error")
        detail = body.get("detail", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        title = "Error"
        detail = str(error)

    exc_class = _STATUS_EXCEPTIONS.get(error.code, FruxonAPIError)
    raise exc_class(status=error.code, title=title, detail=detail) from error


def _parse_execution_result(data: dict) -> ExecutionResult:
    """Parse raw API response into an ExecutionResult."""
    trace_data: dict = data.get("trace", {})
    trace = ExecutionTrace(
        agent_id=trace_data.get("agentId", ""),
        agent_revision=trace_data.get("agentRevision", 0),
        duration=trace_data.get("duration", 0),
        input_cost=trace_data.get("inputCost", 0.0),
        output_cost=trace_data.get("outputCost", 0.0),
        total_cost=trace_data.get("totalCost", 0.0),
    )
    return ExecutionResult(
        response=data.get("response", ""),
        trace=trace,
        session_id=data.get("sessionId", ""),
        links=data.get("links", []),
        execution_record_id=data.get("executionRecordId", ""),
    )
