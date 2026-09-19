from __future__ import annotations

import socket
import time

from gpubox._errors import SshNotReady
from gpubox._models import Instance
from gpubox._protocol import GpuCloud


def ssh_is_open(host: str | None, port: int | None, timeout: float = 1.5) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((str(host), int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            banner = sock.recv(64)
        return banner.startswith(b"SSH-")
    except OSError:
        return False


def wait_until_ssh(
    cloud: GpuCloud,
    instance_id: str,
    *,
    timeout: float = 300,
    interval: float = 2,
) -> Instance:
    """Poll status() until ssh_open is true. Not a Protocol method."""
    deadline = time.monotonic() + timeout
    last: Instance | None = None
    while time.monotonic() < deadline:
        last = cloud.status(instance_id)
        if last.ssh_open:
            return last
        time.sleep(interval)
    raise SshNotReady(
        f"SSH did not open for {instance_id} within {timeout:.0f}s"
        + (f" (status={last.provider_status})" if last else "")
    )
