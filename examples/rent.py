"""List, rank, rent, run, destroy.

Default provider is fake (no wallet). For a real box:

    GPUBOX_PROVIDER=runpod python examples/rent.py

Keys come from the environment (RUNPOD_API_KEY, VAST_API_KEY, LAMBDA_API_KEY).
Never put keys in this file.
"""

from __future__ import annotations

import os
import sys

from gpubox import LaunchSpec, OfferQuery, connect, rank_offers, wait_until_login


def main() -> int:
    provider = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GPUBOX_PROVIDER", "fake")).strip().lower()
    cloud = connect(provider)
    offers = rank_offers(cloud.list_offers(OfferQuery(limit=8)))
    if not offers:
        print("no offers", file=sys.stderr)
        return 1
    box = cloud.create(offers[0].id, LaunchSpec(image="ubuntu:22.04", disk_gb=16, label="gpubox-example"))
    try:
        wait_until_login(cloud, box, timeout=30 if provider == "fake" else 300)
        command = "echo ok" if provider == "fake" else "nvidia-smi"
        print(cloud.run(box, command), end="")
    finally:
        cloud.destroy(box)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
