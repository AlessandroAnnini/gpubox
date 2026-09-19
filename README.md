# gpubox

Rent one GPU box, wait until SSH works, run a command, copy a file, destroy it. The caller owns the job.

This is the product tree for the Prime studio at `~/Projects/gpubox-studio`. Program notes live in `../brief/` and `../memory/`.

## Install

```bash
uv sync --extra vast
# or: uv sync --extra all
```

Extras:

- `gpubox[vast]` pulls `vastai`
- `gpubox[runpod]` is httpx (already in core)
- `gpubox[all]` is both

## Connect

```python
from gpubox import LaunchSpec, OfferQuery, connect, wait_until_ssh

cloud = connect("vast", api_key="...")
offers = cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"], min_disk_gb=50))
box = cloud.create(offers[0].id, LaunchSpec(image="ubuntu:22.04", disk_gb=50))
wait_until_ssh(cloud, box)
cloud.run(box, "nvidia-smi")
cloud.destroy(box)
```

`wait_until_ssh` and `ssh_is_open` are helpers. They are not methods on `GpuCloud`.

RunPod is the same Protocol. Offer ids are SKUs of the form `gpu|SECURE` or `gpu|COMMUNITY`. GPU name strings stay in the provider's spelling. Do not treat `RTX_4090` and `NVIDIA GeForce RTX 4090` as the same id.

```python
from pathlib import Path
from gpubox import OfferQuery, connect

cloud = connect(
    "runpod",
    api_key="...",
    ssh_key=Path.home() / ".runpod" / "ssh" / "runpodctl-ssh-key",
)
offers = cloud.list_offers(OfferQuery(gpu_names=["NVIDIA GeForce RTX 4090"]))
# offers[0].id == "NVIDIA GeForce RTX 4090|SECURE"
```

Tests and local callers can skip the network:

```python
from gpubox import FakeCloud, connect

cloud = connect("fake")
assert isinstance(cloud, FakeCloud)
```

`StudioCloud` is a type alias for `GpuCloud`. Prefer `GpuCloud`.

## Errors

- `AuthError` — missing or rejected API key
- `NotFound` — instance or offer is gone
- `Unavailable` — offer cancelled or no capacity
- `SshNotReady` — SSH host/port not published, or banner not up
- `ProviderError` — other vendor failure (`provider`, `status_code`, `detail`)

## Again as a caller

Again should build `LaunchSpec` from its own settings. If it still wants `/workspace/READY` or a 4-hour kill switch, pass those in `start_command` and `max_hours`. The library will not write READY or apply boot-watch timers. `status()` reports provider state plus `ssh_open`. It has no `ready` field. Map `Instance.ssh_open` plus your own probe onto studio phases.

## Tests

```bash
uv run pytest -q
```

Tests use `FakeCloud` and injected vendor clients. They do not rent GPUs. Live checks are opt-in only: `GPUBOX_LIVE=1`.

## Secrets

Copy `.env.example` if you want local keys. Never commit `.env`.
