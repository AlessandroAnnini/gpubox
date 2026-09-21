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
    "rank_offers",
    "ssh_is_open",
    "wait_until_login",
    "wait_until_ssh",
]
