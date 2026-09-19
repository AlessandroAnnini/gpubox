# gpubox

Rent one GPU box, wait until SSH works, run a command, copy a file, destroy it. The caller owns the job.

This is the product tree for the Prime studio at `~/Projects/gpubox-studio`. Program notes live in `../brief/` and `../memory/`.

## Install

```bash
uv sync --extra vast
# or: uv sync --extra all
```

```python
from gpubox import LaunchSpec, OfferQuery, connect, wait_until_ssh

cloud = connect("vast", api_key="...")
offers = cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"], min_disk_gb=50))
box = cloud.create(offers[0].id, LaunchSpec(image="ubuntu:22.04", disk_gb=50))
wait_until_ssh(cloud, box)
cloud.run(box, "nvidia-smi")
cloud.destroy(box)
```

RunPod is the same Protocol:

```python
from pathlib import Path
from gpubox import connect

cloud = connect(
    "runpod",
    api_key="...",
    ssh_key=Path.home() / ".runpod" / "ssh" / "runpodctl-ssh-key",
)
```

Extras: `gpubox[vast]` pulls `vastai`. `gpubox[runpod]` is httpx (already in core). `gpubox[all]` is both.

`StudioCloud` is a type alias for `GpuCloud`. Prefer `GpuCloud`.

## Again as a caller

Again should build `LaunchSpec` from its own settings. If it still wants `/workspace/READY` or a 4-hour kill switch, pass those in `start_command` and `max_hours`. The library will not write READY or apply boot-watch timers. Map `Instance.ssh_open` plus your own probe onto studio phases.

## Tests

```bash
uv run pytest -q
```

Tests use `FakeCloud` and injected vendor clients. They do not rent GPUs. Live checks are opt-in only: `GPUBOX_LIVE=1`.

## Secrets

Copy `.env.example` if you want local keys. Never commit `.env`.
