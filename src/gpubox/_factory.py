from __future__ import annotations

import os
from pathlib import Path

from gpubox._errors import AuthError
from gpubox._models import ClientConfig
from gpubox._protocol import GpuCloud

ENV_KEYS = {
    "vast": "VAST_API_KEY",
    "vastai": "VAST_API_KEY",
    "runpod": "RUNPOD_API_KEY",
    "lambda": "LAMBDA_API_KEY",
    "lambdalabs": "LAMBDA_API_KEY",
}
ENV_SSH = {
    "runpod": "RUNPOD_SSH_KEY",
    "lambda": "LAMBDA_SSH_KEY",
    "lambdalabs": "LAMBDA_SSH_KEY",
}


def _env_value(name: str, table: dict[str, str]) -> str:
    key = table.get(name)
    if not key:
        return ""
    return (os.environ.get(key) or "").strip()


def connect(provider: str, api_key: str = "", **kwargs: object) -> GpuCloud:
    """Return a GpuCloud. Lazy-imports the vendor adapter."""
    name = (provider or "").strip().lower()
    ssh_key = kwargs.pop("ssh_key", None)
    timeout = float(kwargs.pop("timeout", 30.0) or 30.0)
    client = kwargs.pop("client", None)
    if kwargs:
        unknown = ", ".join(sorted(str(key) for key in kwargs))
        raise TypeError(f"unexpected connect() arguments: {unknown}")

    api = (api_key or "").strip() or _env_value(name, ENV_KEYS)
    ssh = ssh_key
    if ssh is None or (isinstance(ssh, str) and not str(ssh).strip()):
        ssh = _env_value(name, ENV_SSH) or None
    key_path = Path(ssh) if ssh else None
    config = ClientConfig(api_key=api, ssh_key=key_path, timeout=timeout)

    if name in {"fake", "memory"}:
        from gpubox.testing import FakeCloud

        return FakeCloud()
    if name == "runpod":
        from gpubox.adapters.runpod import RunPodCloud

        if not config.api_key:
            raise AuthError("RUNPOD_API_KEY is required when provider is runpod.")
        return RunPodCloud(config, client=client)  # type: ignore[arg-type]
    if name in {"lambda", "lambdalabs"}:
        from gpubox.adapters.lambdalabs import LambdaCloud

        if not config.api_key:
            raise AuthError("LAMBDA_API_KEY is required when provider is lambda.")
        return LambdaCloud(config, client=client)  # type: ignore[arg-type]
    if name in {"vast", "vastai"}:
        from gpubox.adapters.vast import VastCloud

        if client is None and not config.api_key:
            raise AuthError("VAST_API_KEY is required when provider is vast.")
        return VastCloud(config, client=client)
    raise ValueError(f"unknown provider: {provider!r}")
