from __future__ import annotations

from typing import Any


class GpuBoxError(Exception):
    """Base error for the gpubox machine API."""


class AuthError(GpuBoxError):
    """Missing or rejected API key."""


class NotFound(GpuBoxError):
    """Instance or offer is gone."""


class Unavailable(GpuBoxError):
    """Offer cancelled or the provider has no capacity."""


class SshNotReady(GpuBoxError):
    """SSH host or port is not published yet, or the banner is not up."""


class ProviderError(GpuBoxError):
    """Vendor call failed. status_code and detail are optional."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
