# gpubox

Rent one GPU box, wait until SSH works, run a command, copy a file, destroy it. The caller owns the job.

MIT licensed. The public API is 0.x. Pin it from `VERSION` (also the hatch version). Do not publish to PyPI until a second consumer exists.

## Install

From a checkout:

```bash
uv sync --extra vast
# or: uv sync --extra all
```

Extras:

- `gpubox[vast]` pulls `vastai`
- `gpubox[runpod]` is httpx (already in core)
- `gpubox[lambda]` is httpx (already in core)
- `gpubox[all]` is all three

## Connect

```python
from gpubox import LaunchSpec, OfferQuery, connect, rank_offers, wait_until_ssh

cloud = connect("vast", api_key="...")
offers = cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"], min_disk_gb=50))
offers = rank_offers(offers, reliability_weight=0.1)
box = cloud.create(offers[0].id, LaunchSpec(image="ubuntu:22.04", disk_gb=50))
wait_until_ssh(cloud, box)
cloud.run(box, "nvidia-smi")
cloud.destroy(box)
```

`rank_offers` is arithmetic on one provider list. Score is `price_weight * price_per_hour - reliability_weight * (reliability or 0) - disk_weight * (disk_space or 0)`; lower wins; non-finite price last. It is not a Protocol method and does not merge clouds.

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

Lambda is the same Protocol. Offer ids are SKUs of the form `instance_type|region`. GPU names stay in Lambda's `gpu_description` spelling. SSH user is `ubuntu`. `disk_gb` and `max_hours` are not Lambda API fields.

```python
from pathlib import Path
from gpubox import LaunchSpec, OfferQuery, connect

cloud = connect("lambda", api_key="...", ssh_key=Path.home() / ".ssh" / "id_ed25519")
offers = cloud.list_offers(OfferQuery(gpu_names=["A100 SXM4"], raw="us-west-1"))
# offers[0].id == "gpu_1x_a100|us-west-1"
box = cloud.create(
    offers[0].id,
    LaunchSpec(image="ubuntu-lts", label="box", extra={"ssh_key_name": "gpubox"}),
)
```

Tests and local callers can skip the network:

```python
from gpubox import FakeCloud, connect

cloud = connect("fake")
assert isinstance(cloud, FakeCloud)
```

`StudioCloud` is a type alias for `GpuCloud`. Prefer `GpuCloud`.

## Errors

- `GpuBoxError` — base class for the errors below
- `AuthError` — missing or rejected API key
- `NotFound` — instance or offer is gone
- `Unavailable` — offer cancelled or no capacity
- `SshNotReady` — SSH host/port not published, or banner not up
- `ProviderError` — other vendor failure (`provider`, `status_code`, `detail`)

## Caller owns the job

`status()` reports provider state plus `ssh_open`. It never reads or writes `/workspace/READY`. Boot-watch timers and workspace probes stay in the caller. The library will not write READY, mkdir a workspace, or apply those timers unless the caller passed them in `LaunchSpec`.

```python
from gpubox import LaunchSpec

spec = LaunchSpec(
    image="ubuntu:22.04",
    disk_gb=50,
    label="box",
    start_command="mkdir -p /workspace && echo ready > /workspace/READY",
    max_hours=4,
)
box = cloud.create(offer_id, spec)
inst = cloud.status(box)
# caller: ssh_open + own READY probe
# never expect inst.ready; that field does not exist
```

## Tests

```bash
uv run --project . --directory . --reinstall-package gpubox pytest -q
```

Tests use `FakeCloud` and injected vendor clients. They do not rent GPUs. Live checks are opt-in only: `GPUBOX_LIVE=1`.

## Secrets

Copy `.env.example` if you want local keys. Never commit `.env`.
