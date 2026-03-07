"""Exceptions for the Fruxon SDK."""

from pathlib import Path


class FruxonError(Exception):
    """Base exception for all Fruxon SDK errors."""


class FruxonAPIError(FruxonError):
    """Raised when the Fruxon API returns an error response."""

    def __init__(self, status: int, title: str, detail: str):
        self.status = status
        self.title = title
        self.detail = detail
        super().__init__(f"{status} {title}: {detail}")


class AuthenticationError(FruxonAPIError):
    """Raised on 401 Unauthorized responses."""


class ForbiddenError(FruxonAPIError):
    """Raised on 403 Forbidden responses."""


class NotFoundError(FruxonAPIError):
    """Raised on 404 Not Found responses."""


class ValidationError(FruxonAPIError):
    """Raised on 400 or 422 responses."""


class FruxonConnectionError(FruxonError):
    """Raised when the API is unreachable."""


class MultipleAgentsError(FruxonError):
    """Raised when multiple agent entry points are detected."""

    def __init__(self, entry_points: list[tuple[Path, str]]):
        self.entry_points = entry_points
        super().__init__(f"Multiple agents detected: {len(entry_points)} entry points found")
