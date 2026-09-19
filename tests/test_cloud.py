from __future__ import annotations

from pathlib import Path

import pytest

from gpubox import (
    AuthError,
    ClientConfig,
    FakeCloud,
    Instance,
    LaunchSpec,
    NotFound,
    Offer,
    OfferQuery,
    ProviderError,
    Unavailable,
    connect,
)
from gpubox.adapters.runpod import RunPodCloud, encode_sku, parse_sku, ssh_from_pod
from gpubox.adapters.vast import VastCloud, instance_from_row, offer_from_row


def test_connect_selects_fake() -> None:
    cloud = connect("fake")
    assert isinstance(cloud, FakeCloud)


def test_connect_selects_runpod() -> None:
    cloud = connect("runpod", api_key="rp-test", client=_FakeHttp())
    assert type(cloud).__name__ == "RunPodCloud"


def test_connect_runpod_requires_key() -> None:
    with pytest.raises(AuthError):
        connect("runpod", api_key="")


def test_connect_selects_vast() -> None:
    cloud = connect("vast", api_key="vast-test", client=_FakeVast())
    assert isinstance(cloud, VastCloud)


def test_connect_unknown() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        connect("lambda", api_key="x")


def test_vast_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    import gpubox.adapters.vast as vast_mod

    def boom() -> None:
        raise ImportError("install gpubox[vast]")

    monkeypatch.setattr(vast_mod, "_require_vastai", boom)
    with pytest.raises(ImportError, match="install gpubox\\[vast\\]"):
        VastCloud(ClientConfig(api_key="k"))


def test_runpod_sku_parse() -> None:
    sku = encode_sku("NVIDIA GeForce RTX 3090", "SECURE")
    assert sku == "NVIDIA GeForce RTX 3090|SECURE"
    gpu, cloud = parse_sku(sku)
    assert gpu == "NVIDIA GeForce RTX 3090"
    assert cloud == "SECURE"


def test_runpod_ssh_from_pod() -> None:
    host, port = ssh_from_pod({"publicIp": "1.2.3.4", "portMappings": {"22": 23456}})
    assert host == "1.2.3.4"
    assert port == 23456


def test_runpod_ssh_ignores_non_ssh_ports() -> None:
    host, port = ssh_from_pod(
        {
            "publicIp": "1.2.3.4",
            "runtime": {
                "ports": [
                    {
                        "ip": "9.9.9.9",
                        "privatePort": 8888,
                        "publicPort": 443,
                    },
                    {
                        "ip": "1.2.3.4",
                        "privatePort": 22,
                        "publicPort": 23456,
                    },
                ]
            },
        }
    )
    assert host == "1.2.3.4"
    assert port == 23456


def test_fake_create_status_destroy() -> None:
    cloud = FakeCloud()
    offer = cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"]))[0]
    box = cloud.create(offer.id, LaunchSpec(image="ubuntu:22.04", label="demo"))
    inst = cloud.status(box)
    assert inst.id == "77"
    assert inst.ssh_open is True
    assert inst.provider_status == "running"
    assert "ready" not in Instance.model_fields
    found = cloud.find("demo")
    assert found is not None
    assert found.id == "77"
    cloud.destroy(box)
    assert cloud.destroyed is True
    gone = cloud.status(box)
    assert gone.id is None


def test_fake_copy_and_run(tmp_path: Path) -> None:
    cloud = FakeCloud()
    box = cloud.create("101", LaunchSpec(image="x"))
    src = tmp_path / "in.bin"
    src.write_bytes(b"abc")
    cloud.upload(box, src, "/workspace/in.bin")
    out = tmp_path / "out.ply"
    cloud.download(box, "/workspace/out.ply", out)
    assert out.read_bytes().startswith(b"ply")
    assert cloud.run(box, "echo hi") == "ok"
    assert cloud.logs(box)


def test_offer_dph_alias() -> None:
    offer = Offer.model_validate({"id": 101, "gpu_name": "RTX_4090", "dph_total": 0.4})
    assert offer.id == "101"
    assert offer.price_per_hour == 0.4
    assert offer.dph_total == 0.4


def test_vast_offer_from_row() -> None:
    offer = offer_from_row(
        {
            "id": 101,
            "gpu_name": "RTX_4090",
            "gpu_ram": 24,
            "dph_total": 0.32,
            "machine_id": 5,
            "host_id": 7,
            "geolocation": "Iceland",
        }
    )
    assert offer.id == "101"
    assert offer.price_per_hour == 0.32
    assert offer.machine_id == 5


def test_vast_instance_has_no_ready() -> None:
    inst = instance_from_row(
        {
            "id": 77,
            "actual_status": "running",
            "gpu_name": "RTX_4090",
            "dph_total": 0.32,
            "ssh_host": "1.2.3.4",
            "ssh_port": 22,
        },
        ssh_open=True,
    )
    assert inst.ssh_open is True
    assert not hasattr(inst, "ready") or "ready" not in inst.model_fields


def test_vast_list_create_status_with_fake_client() -> None:
    client = _FakeVast()
    cloud = VastCloud(ClientConfig(api_key="k"), client=client)
    offers = cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"], exclude_hosts=["9"]))
    assert offers[0].id == "101"
    box = cloud.create(
        offers[0].id,
        LaunchSpec(image="ubuntu:22.04", disk_gb=40, label="box"),
    )
    assert box == "77"
    assert "onstart_cmd" not in client.created[0]
    inst = cloud.status(box)
    assert inst.id == "77"
    assert "ready" not in Instance.model_fields
    found = cloud.find("box")
    assert found is not None
    cloud.destroy(box)
    assert client.destroyed == [77]


def test_vast_create_does_not_write_ready() -> None:
    client = _FakeVast()
    cloud = VastCloud(ClientConfig(api_key="k"), client=client)
    cloud.create("101", LaunchSpec(image="img", start_command="echo hello"))
    assert client.created[0]["onstart_cmd"] == "echo hello"
    assert "READY" not in client.created[0]["onstart_cmd"]


def test_runpod_create_status_with_fake_client() -> None:
    client = _FakeHttp()
    cloud = RunPodCloud(ClientConfig(api_key="k"), client=client)
    sku = encode_sku("NVIDIA GeForce RTX 4090", "SECURE")
    box = cloud.create(sku, LaunchSpec(image="ubuntu:22.04", disk_gb=40, label="box"))
    assert box == "pod-1"
    assert client.created[0]["name"] == "box"
    assert client.created[0]["imageName"] == "ubuntu:22.04"
    assert "terminateAfter" not in client.created[0]
    start = " ".join(client.created[0]["dockerStartCmd"])
    assert "sshd" in start or "service ssh start" in start
    assert "READY" not in start
    inst = cloud.status(box)
    assert inst.id == "pod-1"
    assert inst.label == "box"
    assert "ready" not in Instance.model_fields
    found = cloud.find("box")
    assert found is not None
    cloud.destroy(box)
    assert client.deleted == ["pod-1"]


def test_runpod_create_passes_start_command_and_max_hours() -> None:
    client = _FakeHttp()
    cloud = RunPodCloud(ClientConfig(api_key="k"), client=client)
    cloud.create(
        encode_sku("NVIDIA GeForce RTX 4090", "SECURE"),
        LaunchSpec(image="img", start_command="echo hello", max_hours=4),
    )
    start = " ".join(client.created[0]["dockerStartCmd"])
    assert start.endswith("echo hello")
    assert "READY" not in start
    assert "terminateAfter" in client.created[0]


def test_error_types() -> None:
    assert issubclass(AuthError, Exception)
    err = ProviderError("boom", provider="vast", status_code=500, detail="x")
    assert err.provider == "vast"
    assert err.status_code == 500
    assert str(Unavailable("gone")) == "gone"
    assert str(NotFound("missing")) == "missing"


class _FakeVast:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.destroyed: list[int] = []

    def show_user(self) -> dict:
        return {"username": "alan", "credit": 9}

    def search_offers(self, **kwargs: object) -> list[dict]:
        del kwargs
        return [
            {
                "id": 101,
                "gpu_name": "RTX_4090",
                "gpu_ram": 24,
                "dph_total": 0.32,
                "machine_id": 5,
                "host_id": 7,
                "geolocation": "Iceland",
            }
        ]

    def create_instance(self, offer_id: int, **kwargs: object) -> dict:
        del offer_id
        self.created.append(dict(kwargs))
        return {"success": True, "new_contract": 77}

    def destroy_instance(self, instance_id: int) -> None:
        self.destroyed.append(instance_id)

    def show_instance(self, instance_id: int) -> dict:
        return {
            "id": instance_id,
            "actual_status": "running",
            "gpu_name": "RTX_4090",
            "dph_total": 0.32,
            "ssh_host": "1.2.3.4",
            "ssh_port": 22,
            "label": "box",
        }

    def show_instances(self) -> list[dict]:
        return [self.show_instance(77)]

    def execute(self, instance_id: int, command: str) -> str:
        del instance_id
        return command

    def logs(self, **kwargs: object) -> str:
        del kwargs
        return "log"

    def copy(self, src: str, dst: str) -> dict:
        del src, dst
        return {"success": True}


class _Response:
    def __init__(self, status_code: int = 200, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""
        self.content = b"{}" if payload is not None else b""

    def json(self) -> object:
        return self._payload


class _FakeHttp:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self._pod: dict | None = None

    def request(self, method: str, path: str, **kwargs: object) -> _Response:
        if path == "/user":
            return _Response(200, {"username": "rp", "clientBalance": 3})
        if path == "/gpu-types":
            return _Response(200, [])
        if path == "/pods" and method == "POST":
            payload = dict(kwargs.get("json") or {})
            self.created.append(payload)
            self._pod = {
                "id": "pod-1",
                "name": payload.get("name"),
                "desiredStatus": "RUNNING",
                "publicIp": "1.2.3.4",
                "portMappings": {"22": 23456},
            }
            return _Response(200, {"id": "pod-1"})
        if path == "/pods" and method == "GET":
            return _Response(200, [self._pod] if self._pod else [])
        if path == "/pods/pod-1" and method == "GET":
            return _Response(200, self._pod or {})
        if path == "/pods/pod-1" and method == "DELETE":
            self.deleted.append("pod-1")
            self._pod = None
            return _Response(200, {})
        return _Response(200, {})

    def close(self) -> None:
        return None
