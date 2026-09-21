from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

from gpubox._errors import AuthError, ProviderError, SshNotReady
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


def wait_until_login(
    cloud: GpuCloud,
    instance_id: str,
    *,
    timeout: float = 300,
    interval: float = 2,
) -> Instance:
    """Wait for banner, then poll `ssh … true`. Returns Instance. Not a Protocol method."""
    wait_until_ssh(cloud, instance_id, timeout=timeout, interval=interval)
    deadline = time.monotonic() + timeout
    last: Instance | None = None
    while time.monotonic() < deadline:
        last = cloud.status(instance_id)
        try:
            cloud.run(instance_id, "true")
        except AuthError:
            raise
        except ProviderError:
            time.sleep(interval)
            continue
        return last
    raise SshNotReady(
        f"SSH login did not succeed for {instance_id} within {timeout:.0f}s"
        + (f" (status={last.provider_status})" if last else "")
    )


def require_ssh_key(key: Path, provider: str) -> Path:
    if not key.is_file():
        raise AuthError(f"{provider} SSH key missing at {key}")
    return key


def ssh_options(key: Path, port: int, provider: str = "SSH") -> list[str]:
    require_ssh_key(key, provider)
    return [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-i",
        str(key),
        "-p",
        str(port),
    ]


def _raise_ssh_failure(detail: str, *, provider: str) -> None:
    text = (detail or "").strip() or "ssh failed"
    lowered = text.lower()
    if "permission denied" in lowered or "publickey" in lowered:
        raise AuthError(
            f"{provider}: SSH login failed (public key). The instance is already running. "
            "Add the matching .pub to the provider account (RunPod: account SSH keys, "
            "not RUNPOD_SSH_KEY) and retry."
        )
    raise ProviderError(text, provider=provider)


def run_ssh(key: Path, host: str, port: int, user: str, command: str, *, provider: str) -> str:
    result = subprocess.run(
        ["ssh", *ssh_options(key, port, provider), f"{user}@{host}", command],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        _raise_ssh_failure(result.stderr or result.stdout or "ssh failed", provider=provider)
    return result.stdout


def run_scp(key: Path, host: str, port: int, src: str, dst: str, *, provider: str) -> None:
    require_ssh_key(key, provider)
    result = subprocess.run(
        [
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-P",
            str(port),
            "-i",
            str(key),
            src,
            dst,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        _raise_ssh_failure(result.stderr or result.stdout or "scp failed", provider=provider)
