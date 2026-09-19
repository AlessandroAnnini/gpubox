from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from gpubox._errors import AuthError, NotFound, ProviderError, SshNotReady, Unavailable
from gpubox._models import Account, ClientConfig, Instance, LaunchSpec, Offer, OfferQuery
from gpubox._ssh import ssh_is_open

REST_BASE = "https://cloud.lambda.ai/api/v1"
SSH_USER = "ubuntu"
SSH_PORT = 22
_HEX_ID = re.compile(r"^[0-9a-fA-F]{16,}$")


def encode_sku(instance_type: str, region: str) -> str:
    return f"{instance_type.strip()}|{region.strip()}"


def parse_sku(offer_id: str) -> tuple[str, str]:
    kind, _, region = offer_id.partition("|")
    kind = kind.strip()
    region = region.strip()
    if not kind or not region:
        raise ValueError(f"invalid Lambda sku: {offer_id!r}")
    return kind, region


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload and len(payload) <= 3:
        return payload["data"]
    return payload


def _first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _raise_http(method: str, path: str, status_code: int, detail: str) -> None:
    message = f"Lambda {method} {path} failed ({status_code}): {detail}"
    low = detail.lower()
    if status_code in {401, 403}:
        raise AuthError(message)
    if status_code == 404:
        raise NotFound(message)
    if status_code in {409, 429} or "insufficient-capacity" in low or "quota-exceeded" in low:
        raise Unavailable(message)
    raise ProviderError(message, provider="lambda", status_code=status_code, detail=detail)


def _image_spec(image: str) -> dict[str, str] | None:
    value = (image or "").strip()
    if not value:
        return None
    if "/" in value or (":" in value and not _HEX_ID.match(value)):
        return None
    if _HEX_ID.match(value):
        return {"id": value}
    return {"family": value}


def _user_data(command: str | None) -> str | None:
    if not command:
        return None
    if command.lstrip().startswith("#cloud-config"):
        return command
    escaped = command.replace("'", "'\"'\"'")
    return f"#cloud-config\nruncmd:\n  - bash -lc '{escaped}'\n"


def instance_from_row(row: dict[str, Any], ssh_open: bool = False) -> Instance:
    host = row.get("ip") or row.get("ipv4")
    itype = row.get("instance_type")
    gpu_name = None
    price = _first_number(row, "price_cents_per_hour")
    if isinstance(itype, dict):
        gpu_name = itype.get("gpu_description") or itype.get("name")
        if price is None:
            cents = itype.get("price_cents_per_hour")
            price = float(cents) / 100 if cents is not None else None
    elif isinstance(itype, str):
        gpu_name = itype
    if price is not None and price > 20:
        price = price / 100
    region = row.get("region")
    geo = region.get("name") if isinstance(region, dict) else region
    return Instance(
        id=str(row.get("id")) if row.get("id") is not None else None,
        provider_status=str(row.get("status") or "").lower() or None,
        gpu_name=gpu_name,
        price_per_hour=price,
        geolocation=str(geo) if geo else None,
        ssh_host=str(host) if host else None,
        ssh_port=SSH_PORT if host else None,
        ssh_open=ssh_open,
        label=row.get("name"),
        raw=dict(row),
    )


class LambdaCloud:
    def __init__(self, config: ClientConfig, client: httpx.Client | Any | None = None) -> None:
        if not config.api_key:
            raise AuthError("LAMBDA_API_KEY is required when provider is lambda.")
        self.config = config
        self._http = client or httpx.Client(
            base_url=REST_BASE,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            _raise_http(method, path, response.status_code, response.text[:400])
        if not response.content:
            return None
        return _unwrap(response.json())

    def account(self) -> Account:
        self._request("GET", "/ssh-keys")
        return Account(username="lambda", credit=0, connected=True, email=None)

    def list_offers(self, query: OfferQuery | None = None) -> list[Offer]:
        q = query or OfferQuery()
        catalog = self._request("GET", "/instance-types")
        if not isinstance(catalog, dict):
            return []
        wanted = {name.lower() for name in q.gpu_names} if q.gpu_names else None
        region_filter = (q.raw or "").strip()
        offers: list[Offer] = []
        for key, row in catalog.items():
            if not isinstance(row, dict):
                continue
            itype = row.get("instance_type") if isinstance(row.get("instance_type"), dict) else {}
            name = str(itype.get("name") or key)
            gpu = str(itype.get("gpu_description") or itype.get("description") or name)
            if wanted and gpu.lower() not in wanted and name.lower() not in wanted:
                continue
            storage = itype.get("specs", {}).get("storage_gib") if isinstance(itype.get("specs"), dict) else None
            if q.min_disk_gb is not None and storage is not None and float(storage) < q.min_disk_gb:
                continue
            cents = itype.get("price_cents_per_hour")
            price = float(cents) / 100 if cents is not None else 0.0
            ram = None
            specs = itype.get("specs") if isinstance(itype.get("specs"), dict) else {}
            if specs.get("memory_gib") is not None:
                ram = float(specs["memory_gib"])
            regions = row.get("regions_with_capacity_available") or []
            for region in regions:
                if not isinstance(region, dict):
                    continue
                region_name = str(region.get("name") or "")
                if not region_name:
                    continue
                if region_filter and region_name != region_filter:
                    continue
                offers.append(
                    Offer(
                        id=encode_sku(name, region_name),
                        gpu_name=gpu,
                        gpu_ram=ram,
                        num_gpus=int(specs.get("gpus") or 1),
                        disk_space=float(storage) if storage is not None else None,
                        price_per_hour=price,
                        geolocation=region_name,
                    )
                )
        return offers[: int(q.limit)]

    def create(self, offer_id: str, spec: LaunchSpec) -> str:
        kind, region = parse_sku(offer_id)
        ssh_names = spec.extra.get("ssh_key_names")
        if not ssh_names:
            one = spec.extra.get("ssh_key_name") or "gpubox"
            ssh_names = [one]
        payload: dict[str, Any] = {
            "region_name": region,
            "instance_type_name": kind,
            "ssh_key_names": list(ssh_names),
            "name": spec.label,
        }
        image = _image_spec(spec.image)
        if image:
            payload["image"] = image
        user_data = _user_data(spec.start_command)
        if user_data:
            payload["user_data"] = user_data
        extra = {k: v for k, v in spec.extra.items() if k not in {"ssh_key_name", "ssh_key_names"}}
        payload.update(extra)
        created = self._request("POST", "/instance-operations/launch", json=payload)
        ids = created.get("instance_ids") if isinstance(created, dict) else None
        if not ids:
            raise ProviderError(
                f"Lambda launch did not return an id: {created}",
                provider="lambda",
                detail=created,
            )
        return str(ids[0])

    def destroy(self, instance_id: str) -> None:
        self._request(
            "POST",
            "/instance-operations/terminate",
            json={"instance_ids": [instance_id]},
        )

    def status(self, instance_id: str) -> Instance:
        row = self._get_instance(instance_id)
        host = row.get("ip")
        return instance_from_row(row, ssh_is_open(str(host) if host else None, SSH_PORT if host else None))

    def find(self, label: str) -> Instance | None:
        rows = self._request("GET", "/instances")
        if not isinstance(rows, list):
            return None
        living: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (row.get("name") or "") != label:
                continue
            status = str(row.get("status") or "").lower()
            if status in {"terminated", "terminating"}:
                continue
            living.append(row)
        if not living:
            return None
        row = living[0]
        host = row.get("ip")
        return instance_from_row(row, ssh_is_open(str(host) if host else None, SSH_PORT if host else None))

    def run(self, instance_id: str, command: str) -> str:
        host, port = self._endpoint(instance_id)
        return _run_ssh(self._ssh_key(), host, port, command)

    def upload(self, instance_id: str, local: Path, remote: str) -> None:
        host, port = self._endpoint(instance_id)
        _run_scp(self._ssh_key(), host, port, str(local), f"{SSH_USER}@{host}:{remote}")

    def download(self, instance_id: str, remote: str, local: Path) -> None:
        host, port = self._endpoint(instance_id)
        local.parent.mkdir(parents=True, exist_ok=True)
        _run_scp(self._ssh_key(), host, port, f"{SSH_USER}@{host}:{remote}", str(local))

    def logs(self, instance_id: str) -> str:
        del instance_id
        return ""

    def _get_instance(self, instance_id: str) -> dict[str, Any]:
        raw = self._request("GET", f"/instances/{instance_id}")
        if not isinstance(raw, dict):
            raise NotFound(f"Lambda instance {instance_id} was not found.")
        return raw

    def _endpoint(self, instance_id: str) -> tuple[str, int]:
        row = self._get_instance(instance_id)
        host = row.get("ip")
        if not host:
            raise SshNotReady("Lambda SSH is not published yet.")
        return str(host), SSH_PORT

    def _ssh_key(self) -> Path:
        key = self.config.ssh_key
        if key is None:
            key = Path.home() / ".ssh" / "id_rsa"
        return key


def _ssh_base(key: Path, port: int) -> list[str]:
    if not key.is_file():
        raise AuthError(f"Lambda SSH key missing at {key}")
    return [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-i",
        str(key),
        "-p",
        str(port),
    ]


def _run_ssh(key: Path, host: str, port: int, command: str) -> str:
    result = subprocess.run(
        ["ssh", *_ssh_base(key, port), f"{SSH_USER}@{host}", command],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise ProviderError(
            (result.stderr or result.stdout or "ssh failed").strip(),
            provider="lambda",
        )
    return result.stdout


def _run_scp(key: Path, host: str, port: int, src: str, dst: str) -> None:
    if not key.is_file():
        raise AuthError(f"Lambda SSH key missing at {key}")
    result = subprocess.run(
        [
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "BatchMode=yes",
            "-P",
            str(port),
            "-i",
            str(key),
            src,
            dst,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise ProviderError(
            (result.stderr or result.stdout or "scp failed").strip(),
            provider="lambda",
        )
