from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gpubox._errors import AuthError, NotFound, ProviderError, Unavailable
from gpubox._models import Account, ClientConfig, Instance, LaunchSpec, Offer, OfferQuery
from gpubox._ssh import ssh_is_open


def _require_vastai() -> Any:
    try:
        from vastai import VastAI
    except ImportError as exc:
        raise ImportError("install gpubox[vast]") from exc
    return VastAI


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"expected mapping, got {type(value)!r}")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        for key in ("output", "result", "stdout", "text"):
            if key in value and value[key] is not None:
                return _as_text(value[key])
        return json.dumps(value)
    return str(value)


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


def _as_gib(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 128:
        return round(value / 1024, 1)
    return value


def _ssh_endpoint(row: dict[str, Any]) -> tuple[str | None, int | None]:
    host = row.get("ssh_host") or row.get("public_ipaddr")
    port = row.get("ssh_port")
    if not port:
        ports = row.get("ports") or {}
        mapped = ports.get("22/tcp") or ports.get("22") or []
        if mapped and isinstance(mapped, list):
            port = mapped[0].get("HostPort")
    try:
        return (str(host) if host else None, int(port) if port else None)
    except (TypeError, ValueError):
        return (str(host) if host else None, None)


def offer_from_row(row: dict[str, Any]) -> Offer:
    raw_id = row.get("id") or row.get("ask_id") or 0
    return Offer(
        id=str(raw_id),
        gpu_name=str(row.get("gpu_name") or row.get("gpu_name_unbranded") or "GPU"),
        gpu_ram=_as_gib(_first_number(row, "gpu_ram")),
        num_gpus=int(row.get("num_gpus") or 1),
        cpu_ram=_first_number(row, "cpu_ram"),
        disk_space=_first_number(row, "disk_space"),
        price_per_hour=float(row.get("dph_total") or row.get("dph") or 0),
        geolocation=row.get("geolocation") or row.get("country"),
        reliability=_first_number(row, "reliability", "reliability2"),
        inet_up=_first_number(row, "inet_up"),
        inet_down=_first_number(row, "inet_down"),
        machine_id=int(row["machine_id"]) if row.get("machine_id") is not None else None,
        host_id=int(row["host_id"]) if row.get("host_id") is not None else None,
    )


def instance_from_row(row: dict[str, Any] | None, ssh_open: bool = False) -> Instance:
    if not row:
        return Instance()
    host, port = _ssh_endpoint(row)
    raw_id = row.get("id")
    return Instance(
        id=str(raw_id) if raw_id is not None else None,
        provider_status=row.get("actual_status") or row.get("status_msg"),
        gpu_name=row.get("gpu_name"),
        price_per_hour=_first_number(row, "dph_total", "dph"),
        geolocation=row.get("geolocation"),
        ssh_host=host,
        ssh_port=port,
        ssh_open=ssh_open,
        host_id=int(row["host_id"]) if row.get("host_id") is not None else None,
        machine_id=int(row["machine_id"]) if row.get("machine_id") is not None else None,
        label=row.get("label"),
        raw=dict(row),
    )


def _vast_query(query: OfferQuery) -> str:
    if query.raw:
        return query.raw
    parts = ["verified=true", "rentable=true", "num_gpus=1"]
    if query.gpu_names:
        names = ",".join(query.gpu_names)
        parts.append(f"gpu_name in [{names}]")
    if query.min_disk_gb is not None:
        parts.append(f"disk_space>={int(query.min_disk_gb)}")
    return " ".join(parts)


def _raise_vast(result: dict[str, Any], *, action: str) -> None:
    msg = str(result.get("error") or result.get("msg") or result)
    low = msg.lower()
    if "unavail" in low or "no longer" in low or "not available" in low:
        raise Unavailable(msg)
    raise ProviderError(f"Vast {action} failed: {msg}", provider="vast", detail=result)


class VastCloud:
    def __init__(self, config: ClientConfig, client: Any = None) -> None:
        if client is None and not config.api_key:
            raise AuthError("VAST_API_KEY is required when provider is vast.")
        self.config = config
        if client is None:
            VastAI = _require_vastai()
            client = VastAI(api_key=config.api_key, raw=True, quiet=True)
        self.client = client

    def account(self) -> Account:
        raw = _as_dict(self.client.show_user())
        user = raw.get("user") if isinstance(raw.get("user"), dict) else raw
        credit = user.get("credit") or user.get("balance") or 0
        return Account(
            username=user.get("username") or user.get("fullname") or "vast",
            email=user.get("email"),
            credit=float(credit or 0),
            connected=True,
        )

    def list_offers(self, query: OfferQuery | None = None) -> list[Offer]:
        q = query or OfferQuery()
        blocked = {item for item in q.exclude_hosts if item}
        rows = self.client.search_offers(
            query=_vast_query(q),
            type="on-demand",
            order="dph_total",
            limit=int(q.limit),
            storage=float(q.min_disk_gb or 0),
        )
        if not isinstance(rows, list):
            rows = rows.get("offers") if isinstance(rows, dict) else []
        offers = [offer_from_row(_as_dict(row)) for row in rows or []]
        return [
            offer
            for offer in offers
            if offer.id
            and (offer.machine_id is None or str(offer.machine_id) not in blocked)
            and (offer.host_id is None or str(offer.host_id) not in blocked)
        ]

    def create(self, offer_id: str, spec: LaunchSpec) -> str:
        payload: dict[str, Any] = {
            "image": spec.image,
            "disk": float(spec.disk_gb),
            "ssh": spec.ssh,
            "direct": True,
            "label": spec.label,
            "cancel_unavail": True,
        }
        if spec.start_command:
            payload["onstart_cmd"] = spec.start_command
        payload.update(spec.extra)
        result = _as_dict(self.client.create_instance(int(offer_id), **payload))
        if not result.get("success") and "new_contract" not in result:
            _raise_vast(result, action="create")
        contract = result.get("new_contract") or result.get("instance_id")
        if contract is None:
            raise ProviderError(
                f"Vast create did not return an id: {result}",
                provider="vast",
                detail=result,
            )
        return str(contract)

    def destroy(self, instance_id: str) -> None:
        self.client.destroy_instance(int(instance_id))

    def status(self, instance_id: str) -> Instance:
        row = self._show_instance(instance_id)
        if not row:
            raise NotFound(f"Vast instance {instance_id} was not found.")
        host, port = _ssh_endpoint(row)
        return instance_from_row(row, ssh_is_open(host, port))

    def find(self, label: str) -> Instance | None:
        living: list[dict[str, Any]] = []
        for row in self._show_instances():
            if (row.get("label") or "") != label:
                continue
            if row.get("actual_status") in {"exited"}:
                continue
            living.append(row)
        if not living:
            return None
        living.sort(key=lambda row: row.get("start_date") or 0, reverse=True)
        row = living[0]
        host, port = _ssh_endpoint(row)
        return instance_from_row(row, ssh_is_open(host, port))

    def run(self, instance_id: str, command: str) -> str:
        return _as_text(self.client.execute(int(instance_id), command))

    def logs(self, instance_id: str) -> str:
        return _as_text(self.client.logs(instance_id=int(instance_id), tail="80"))

    def upload(self, instance_id: str, local: Path, remote: str) -> None:
        self._copy(f"local:{local}", f"C.{instance_id}:{remote}")

    def download(self, instance_id: str, remote: str, local: Path) -> None:
        self._copy(f"C.{instance_id}:{remote}", f"local:{local}")

    def _copy(self, src: str, dst: str) -> None:
        result = self.client.copy(src, dst)
        if isinstance(result, dict) and result.get("success") is False:
            raise ProviderError(
                str(result.get("error") or result.get("msg") or result),
                provider="vast",
                detail=result,
            )

    def _show_instances(self) -> list[dict[str, Any]]:
        rows = self.client.show_instances()
        if not isinstance(rows, list):
            return []
        return [_as_dict(row) for row in rows]

    def _show_instance(self, instance_id: str) -> dict[str, Any] | None:
        row = self.client.show_instance(int(instance_id))
        if row is None:
            return None
        if isinstance(row, list):
            return _as_dict(row[0]) if row else None
        return _as_dict(row)
