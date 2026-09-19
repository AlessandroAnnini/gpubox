from __future__ import annotations

from pathlib import Path

from gpubox._errors import AuthError
from gpubox._models import ClientConfig
from gpubox._protocol import GpuCloud


def connect(provider: str, api_key: str = "", **kwargs: object) -> GpuCloud:
    """Return a GpuCloud. Lazy-imports the vendor adapter."""
    name = (provider or "").strip().lower()
    ssh_key = kwargs.pop("ssh_key", None)
    timeout = float(kwargs.pop("timeout", 30.0) or 30.0)
    client = kwargs.pop("client", None)
    if kwargs:
        unknown = ", ".join(sorted(str(key) for key in kwargs))
        raise TypeError(f"unexpected connect() arguments: {unknown}")

    key_path = Path(ssh_key) if ssh_key else None
    config = ClientConfig(api_key=api_key, ssh_key=key_path, timeout=timeout)

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
