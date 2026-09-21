from importlib.metadata import version as pkg_version

from gpubox._errors import (
    AuthError,
    GpuBoxError,
    NotFound,
    ProviderError,
    SshNotReady,
    Unavailable,
)
from gpubox._factory import connect
from gpubox._models import (
    Account,
    ClientConfig,
    Instance,
    LaunchSpec,
    Offer,
    OfferQuery,
)
from gpubox._protocol import GpuCloud
from gpubox._rank import rank_offers
from gpubox._ssh import ssh_is_open, wait_until_login, wait_until_ssh
from gpubox.testing import FakeCloud


def ensure_ssh_key(cloud: object, pub_path: object = None) -> str:
    """RunPod-only. Lazy-imports the adapter. Not a GpuCloud method."""
    from pathlib import Path

    from gpubox.adapters.runpod import ensure_ssh_key as _impl

    path = Path(pub_path) if pub_path is not None else None
    return _impl(cloud, pub_path=path)


__version__ = pkg_version("gpubox")

__all__ = [
    "__version__",
    "Account",
    "AuthError",
    "ClientConfig",
    "FakeCloud",
    "GpuBoxError",
    "GpuCloud",
    "Instance",
    "LaunchSpec",
    "NotFound",
    "Offer",
    "OfferQuery",
    "ProviderError",
    "SshNotReady",
    "Unavailable",
    "connect",
    "ensure_ssh_key",
    "rank_offers",
    "ssh_is_open",
    "wait_until_login",
    "wait_until_ssh",
]
