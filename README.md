<p align="center">
  <img src="docs/hero.png" alt="gpubox — rent. ssh. run. destroy." width="960" />
</p>

# gpubox

Rent one GPU box, wait until SSH works, run a command, copy a file, destroy it. The caller owns the job.

Live check 2026-09-19: RunPod NVIDIA RTX A4000 at $0.17/hr; created, `nvidia-smi`, destroyed.

Smoke-test an offer, run a command you already have, or copy a file up and back. Details: [when to use it](https://alessandroannini.github.io/gpubox/#when).

Docs: [alessandroannini.github.io/gpubox](https://alessandroannini.github.io/gpubox/).

## Install

```bash
uv add "gpubox[all] @ git+https://github.com/AlessandroAnnini/gpubox"
# or: pip install "gpubox[vast] @ git+https://github.com/AlessandroAnnini/gpubox"
```

PyPI is later, on purpose. From a checkout: `uv sync --extra vast` or `uv sync --extra all`.

```bash
gpubox --version
gpubox list -p runpod --gpu "NVIDIA RTX A4000" --raw COMMUNITY --rank
gpubox rent -p runpod --gpu "NVIDIA RTX A4000" --cmd nvidia-smi
gpubox list -p vast --gpu RTX_4090 --rank
```

`rent` ranks, takes the first offer, then always destroys. After `.env`, `connect("runpod")` is valid: API keys come from `VAST_API_KEY` / `RUNPOD_API_KEY` / `LAMBDA_API_KEY` or `--api-key`. Empty `api_key=""` means env. RunPod and Lambda private-key paths come from `--ssh-key` or `RUNPOD_SSH_KEY` / `LAMBDA_SSH_KEY`. The matching `.pub` must already be on the provider account (RunPod: account SSH keys — that is not `RUNPOD_SSH_KEY`). `ensure_ssh_key(cloud)` appends that `.pub` on RunPod only; it does not replace existing keys. If the vendor call cannot append, add the key in the RunPod console.

`wait_until_ssh` is the TCP banner (`ssh_open`). `wait_until_login` then polls `ssh … true`. Both return `Instance` (`id`, `ssh_host`, `ssh_port`, `ssh_open`). There is no `Box` type; `create` stays `str`. Keep that id and `try` / `finally: destroy`. `rent` still always destroys.

```python
from gpubox import LaunchSpec, OfferQuery, connect, rank_offers, wait_until_login

cloud = connect("runpod")
offers = rank_offers(cloud.list_offers(OfferQuery(gpu_names=["NVIDIA RTX A4000"])))
box = cloud.create(offers[0].id, LaunchSpec(image="ubuntu:22.04", disk_gb=50))
try:
    inst = wait_until_login(cloud, box)
    cloud.run(inst.id or box, "nvidia-smi")
finally:
    cloud.destroy(box)
```

`uv run --project . examples/rent.py` does the same loop on `FakeCloud` (no wallet).

## Providers

- **RunPod** — live-proven (receipt above). Offer ids are `gpu|SECURE` or `gpu|COMMUNITY`.
- **Vast** — adapter; marketplace GPU names; not in the receipt.
- **Lambda** — adapter; not live-proven. Offer ids are `instance_type|region`.

## Rank

`rank_offers` is arithmetic on one provider list. Score is `price_weight * price_per_hour - reliability_weight * reliability - disk_weight * disk_space`; missing or non-finite reliability/disk count as 0; non-finite price last. It does not merge clouds.

## Errors

- `GpuBoxError` — base class for the errors below
- `AuthError` — missing or rejected API key, missing SSH key file, or publickey denial
- `NotFound` — instance or offer is gone
- `Unavailable` — offer cancelled or no capacity
- `SshNotReady` — SSH host or port not published, banner not up, or login wait timed out
- `ProviderError` — other vendor failure (`provider`, `status_code`, `detail`)

## Provider quirks

GPU name strings stay in the provider's spelling. `RTX_4090` and `NVIDIA GeForce RTX 4090` are not the same id.

`status()` reports provider state plus `ssh_open`. It never reads or writes `/workspace/READY`. Pass that probe in `LaunchSpec.start_command` if you want it.

`connect("fake")` returns `FakeCloud` for tests.

## Tests

```bash
uv run --project . --directory . --reinstall-package gpubox pytest -q
```

Tests use `FakeCloud` and injected vendor clients. They do not rent GPUs. Live checks are opt-in only: `GPUBOX_LIVE=1`.

## Secrets

Copy `.env.example` if you want local keys. Never commit `.env`.
