from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest

import gpubox


def _pin() -> str:
    return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0].strip()


def test_package_version_matches_version_file() -> None:
    assert version("gpubox") == _pin()


def test_dunder_version_matches_version_file() -> None:
    assert gpubox.__version__ == _pin()
    assert "__version__" in gpubox.__all__


def test_public_export_drops_studio_aliases() -> None:
    assert "MemoryCloud" not in gpubox.__all__
    assert "StudioCloud" not in gpubox.__all__
    assert "FakeCloud" in gpubox.__all__
    assert "GpuCloud" in gpubox.__all__
    with pytest.raises(ImportError):
        from gpubox import MemoryCloud
    with pytest.raises(ImportError):
        from gpubox import StudioCloud
