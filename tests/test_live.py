"""Live GPU rentals. Default CI never runs these."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

from gpubox import LaunchSpec, Offer, OfferQuery, Unavailable, connect, rank_offers, wait_until_ssh

_live = pytest.mark.skipif(
    os.environ.get("GPUBOX_LIVE") != "1",
    reason="Live GPU tests require GPUBOX_LIVE=1",
)

PRICE_CAP = 0.40
LABEL = f"gpubox-live-{date.today().strftime('%Y%m%d')}"


def ids_to_destroy(created: set[str], snapshot: set[str]) -> set[str]:
    return {item for item in created if item and item not in snapshot}


def test_never_destroy_snapshot_ids() -> None:
    assert ids_to_destroy({"new", "old"}, {"old", "other"}) == {"new"}


def _snapshot_vast(cloud: Any) -> set[str]:
    return {
        str(row.get("id"))
        for row in cloud._show_instances()
        if row.get("id") is not None
    }


def _snapshot_runpod(cloud: Any) -> set[str]:
    from gpubox.adapters.runpod import _as_list

    return {
        str(row.get("id"))
        for row in _as_list(cloud._request("GET", "/pods"))
        if isinstance(row, dict) and row.get("id")
    }


_RUNPOD_SKUS = (
    "NVIDIA RTX A4000",
    "NVIDIA RTX A5000",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 3090",
)


def _rent(cloud: Any, offers: list[Offer], *, image: str) -> str:
    ranked = rank_offers(offers)
    if not ranked or ranked[0].price_per_hour > PRICE_CAP:
        pytest.skip(f"cheapest offer over {PRICE_CAP}/hr or empty")
    return cloud.create(
        ranked[0].id,
        LaunchSpec(image=image, disk_gb=16, label=LABEL),
    )


def _rent_runpod(cloud: Any, *, image: str) -> str:
    last: Exception | None = None
    for gpu in _RUNPOD_SKUS:
        offers = cloud.list_offers(OfferQuery(gpu_names=[gpu], raw="COMMUNITY", limit=4))
        ranked = rank_offers(offers)
        if not ranked or ranked[0].price_per_hour > PRICE_CAP:
            continue
        try:
            return cloud.create(
                ranked[0].id,
                LaunchSpec(image=image, disk_gb=16, label=LABEL),
            )
        except Unavailable as exc:
            last = exc
            continue
    pytest.skip(f"no RunPod COMMUNITY capacity under {PRICE_CAP}/hr ({last})")


@_live
@pytest.mark.skipif(not os.environ.get("VAST_API_KEY"), reason="VAST_API_KEY missing")
def test_live_vast_snapshot_rent_destroy() -> None:
    cloud = connect("vast", api_key=os.environ["VAST_API_KEY"])
    snapshot = _snapshot_vast(cloud)
    created: set[str] = set()
    try:
        box = _rent(
            cloud,
            cloud.list_offers(OfferQuery(gpu_names=["RTX_4090", "RTX_3090"], limit=8)),
            image="nvidia/cuda:12.4.1-base-ubuntu22.04",
        )
        if box:
            created.add(box)
            wait_until_ssh(cloud, box, timeout=300)
            out = cloud.run(box, "nvidia-smi")
            assert "NVIDIA" in out or "nvidia" in out.lower()
    finally:
        for item in ids_to_destroy(created, snapshot):
            cloud.destroy(item)
    assert snapshot <= _snapshot_vast(cloud) | created


@_live
@pytest.mark.skipif(not os.environ.get("RUNPOD_API_KEY"), reason="RUNPOD_API_KEY missing")
def test_live_runpod_snapshot_rent_destroy() -> None:
    from pathlib import Path

    cloud = connect(
        "runpod",
        api_key=os.environ["RUNPOD_API_KEY"],
        ssh_key=Path.home() / ".runpod" / "ssh" / "runpodctl-ssh-key",
    )
    snapshot = _snapshot_runpod(cloud)
    created: set[str] = set()
    try:
        box = _rent_runpod(
            cloud,
            image="runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
        )
        if box:
            created.add(box)
            wait_until_ssh(cloud, box, timeout=300)
            out = cloud.run(box, "nvidia-smi")
            assert "NVIDIA" in out or "nvidia" in out.lower()
    finally:
        for item in ids_to_destroy(created, snapshot):
            cloud.destroy(item)
