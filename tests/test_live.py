"""Live GPU rentals. Default CI never runs these."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GPUBOX_LIVE") != "1",
    reason="Live GPU tests require GPUBOX_LIVE=1",
)


def test_live_opt_in_documented() -> None:
    assert os.environ.get("GPUBOX_LIVE") == "1"
