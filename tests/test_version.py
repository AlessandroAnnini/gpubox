from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest

import gpubox


def test_package_version_matches_version_file() -> None:
    pin = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8")
    assert version("gpubox") == pin.strip().splitlines()[0].strip()


def test_public_export_drops_studio_aliases() -> None:
    assert "MemoryCloud" not in gpubox.__all__
    assert "StudioCloud" not in gpubox.__all__
    assert "FakeCloud" in gpubox.__all__
    assert "GpuCloud" in gpubox.__all__
    with pytest.raises(ImportError):
        from gpubox import MemoryCloud
    with pytest.raises(ImportError):
        from gpubox import StudioCloud
