from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from gpubox._errors import AuthError, NotFound, ProviderError, SshNotReady, Unavailable
from gpubox._models import Account, ClientConfig, Instance, LaunchSpec, Offer, OfferQuery
from gpubox._ssh import run_scp, run_ssh, ssh_is_open

REST_BASE = "https://rest.runpod.io/v1"
GRAPHQL_URL = "https://api.runpod.io/graphql"

DEFAULT_SSH_CMD = (
    "apt-get update && "
    "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server && "
    "mkdir -p /root/.ssh && chmod 700 /root/.ssh && "
    "if [ -n \"$PUBLIC_KEY\" ]; then echo \"$PUBLIC_KEY\" >> /root/.ssh/authorized_keys; fi && "
    "chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true && "
    "ssh-keygen -A && "
    "(service ssh start || /usr/sbin/sshd) && "
    "sleep infinity"
)

DEFAULT_GPU_TYPES = (
    "NVIDIA GeForce RTX 3090",
    "NVIDIA GeForce RTX 4090",
)

FALLBACK_PRICES: dict[tuple[str, str], float] = {
    ("NVIDIA GeForce RTX 3090", "SECURE"): 0.50,
    ("NVIDIA GeForce RTX 3090", "COMMUNITY"): 0.22,
    ("NVIDIA GeForce RTX 4090", "SECURE"): 0.74,
    ("NVIDIA GeForce RTX 4090", "COMMUNITY"): 0.34,
}

FALLBACK_RAM: dict[str, float] = {
    "NVIDIA GeForce RTX 3090": 24,
    "NVIDIA GeForce RTX 4090": 24,
}


def encode_sku(gpu_type: str, cloud: str) -> str:
    return f"{gpu_type.strip()}|{cloud.strip().upper()}"


def parse_sku(offer_id: str) -> tuple[str, str]:
    gpu, _, cloud = offer_id.partition("|")
    gpu = gpu.strip()
    cloud = (cloud or "SECURE").strip().upper()
    if not gpu:
        raise ValueError(f"invalid RunPod sku: {offer_id!r}")
    if cloud not in {"SECURE", "COMMUNITY"}:
        raise ValueError(f"invalid RunPod cloud tier in sku: {offer_id!r}")
    return gpu, cloud


def ssh_from_pod(pod: dict[str, Any]) -> tuple[str | None, int | None]:
    runtime = pod.get("runtime") if isinstance(pod.get("runtime"), dict) else {}
    ssh = pod.get("ssh") if isinstance(pod.get("ssh"), dict) else {}
    runtime_ssh = runtime.get("ssh") if isinstance(runtime.get("ssh"), dict) else {}
    mappings = pod.get("portMappings") or runtime.get("portMappings") or {}
    host = (
        pod.get("publicIp")
        or runtime.get("publicIp")
        or ssh.get("ip")
        or ssh.get("host")
        or runtime_ssh.get("ip")
        or runtime_ssh.get("host")
    )
    port: Any = mappings.get("22") if isinstance(mappings, dict) else None
    port = port or ssh.get("port") or runtime_ssh.get("port")
    ports = runtime.get("ports") or pod.get("runtimePorts") or []
    if isinstance(ports, list):
        for item in ports:
            if not isinstance(item, dict):
                continue
            private = str(item.get("privatePort") or item.get("private") or "")
            if private != "22":
                continue
            host = item.get("ip") or item.get("publicIp") or host
            port = item.get("publicPort") or item.get("public") or port
            break
    try:
        return (str(host) if host else None, int(port) if port else None)
    except (TypeError, ValueError):
        return (str(host) if host else None, None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("pods", "gpuTypes", "data", "items"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
    return []


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
    message = f"RunPod {method} {path} failed ({status_code}): {detail}"
    if status_code in {401, 403}:
        raise AuthError(message)
    if status_code == 404:
        raise NotFound(message)
    if status_code in {409, 422, 429}:
        raise Unavailable(message)
    low = detail.lower()
    if status_code == 500 and "no instances" in low and "available" in low:
        raise Unavailable(message)
    raise ProviderError(message, provider="runpod", status_code=status_code, detail=detail)


def instance_from_pod(pod: dict[str, Any], ssh_open: bool = False) -> Instance:
    host, port = ssh_from_pod(pod)
    machine = pod.get("machine") if isinstance(pod.get("machine"), dict) else {}
    desired = pod.get("desiredStatus")
    runtime = pod.get("runtimeStatus") or pod.get("lastStatusChange")
    if isinstance(runtime, dict):
        runtime = runtime.get("status")
    status = str(desired or runtime or "")
    gpu_name = pod.get("gpuTypeId") or machine.get("gpuTypeId")
    return Instance(
        id=str(pod.get("id")) if pod.get("id") is not None else None,
        provider_status=status.lower() or None,
        gpu_name=gpu_name,
        price_per_hour=_first_number(pod, "costPerHr", "adjustedCostPerHr"),
        geolocation=pod.get("dataCenterId") or machine.get("location"),
        ssh_host=host,
        ssh_port=port,
        ssh_open=ssh_open,
        label=pod.get("name"),
        raw=dict(pod),
    )


class RunPodCloud:
    def __init__(self, config: ClientConfig, client: httpx.Client | Any | None = None) -> None:
        if not config.api_key:
            raise AuthError("RUNPOD_API_KEY is required when provider is runpod.")
        self.config = config
        self._http = client or httpx.Client(
            base_url=REST_BASE,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )
        self._owns_client = client is None
        self._ssh: dict[str, tuple[str | None, int | None]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            _raise_http(method, path, response.status_code, response.text[:400])
        if not response.content:
            return None
        return response.json()

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._owns_client:
            raise ProviderError(
                "RunPod GraphQL is skipped when an HTTP client is injected.",
                provider="runpod",
            )
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        response = httpx.post(
            GRAPHQL_URL,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.config.timeout,
        )
        if response.status_code >= 400:
            _raise_http("POST", "graphql", response.status_code, response.text[:400])
        body = response.json()
        if body.get("errors"):
            raise ProviderError(
                f"RunPod GraphQL error: {body['errors']}",
                provider="runpod",
                detail=body["errors"],
            )
        data = body.get("data")
        if not isinstance(data, dict):
            raise ProviderError("RunPod GraphQL returned no data.", provider="runpod")
        return data

    def account(self) -> Account:
        try:
            raw = self._request("GET", "/user")
            if isinstance(raw, dict):
                user = raw.get("user") if isinstance(raw.get("user"), dict) else raw
                if any(key in user for key in ("clientBalance", "credit", "balance")):
                    credit = user.get("clientBalance") or user.get("credit") or user.get("balance") or 0
                    return Account(
                        username=user.get("username") or user.get("email") or "runpod",
                        email=user.get("email"),
                        credit=float(credit or 0),
                        connected=True,
                    )
        except (AuthError, NotFound):
            raise
        except Exception:
            pass
        if not self._owns_client:
            return Account(username="runpod", credit=0, connected=True)
        data = self._graphql("{ myself { id email clientBalance } }")
        me = data.get("myself") or {}
        return Account(
            username=me.get("email") or me.get("id") or "runpod",
            email=me.get("email"),
            credit=float(me.get("clientBalance") or 0),
            connected=True,
        )

    def list_offers(self, query: OfferQuery | None = None) -> list[Offer]:
        q = query or OfferQuery()
        cloud = (q.raw or "SECURE").strip().upper()
        if cloud not in {"SECURE", "COMMUNITY"}:
            cloud = "SECURE"
        types = list(q.gpu_names) if q.gpu_names else list(DEFAULT_GPU_TYPES)
        catalog = self._gpu_catalog(types)
        offers: list[Offer] = []
        for gpu in types:
            row = catalog.get(gpu, {})
            price_key = "securePrice" if cloud == "SECURE" else "communityPrice"
            price = row.get(price_key)
            if price is None:
                price = FALLBACK_PRICES.get((gpu, cloud))
            if price is None:
                continue
            ram = row.get("memoryInGb") or FALLBACK_RAM.get(gpu)
            offers.append(
                Offer(
                    id=encode_sku(gpu, cloud),
                    gpu_name=gpu,
                    gpu_ram=float(ram) if ram is not None else None,
                    price_per_hour=float(price),
                    geolocation=f"RunPod {cloud.title()}",
                )
            )
        return offers[: int(q.limit)]

    def _gpu_catalog(self, types: list[str]) -> dict[str, dict[str, Any]]:
        try:
            data = self._graphql(
                "{ gpuTypes { id displayName memoryInGb securePrice communityPrice } }"
            )
            rows = data.get("gpuTypes") or []
            catalog: dict[str, dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = row.get("id") or row.get("displayName")
                if name:
                    catalog[str(name)] = row
            if catalog:
                return catalog
        except Exception:
            pass
        try:
            raw = self._request("GET", "/gpu-types")
            catalog = {}
            for item in _as_list(raw):
                if isinstance(item, str):
                    catalog[item] = {"id": item}
                elif isinstance(item, dict):
                    name = item.get("id") or item.get("displayName")
                    if name:
                        catalog[str(name)] = item
            if catalog:
                return catalog
        except Exception:
            pass
        return {name: {"id": name} for name in types}

    def create(self, offer_id: str, spec: LaunchSpec) -> str:
        gpu, cloud = parse_sku(offer_id)
        start = spec.start_command if spec.start_command else DEFAULT_SSH_CMD
        payload: dict[str, Any] = {
            "name": spec.label,
            "imageName": spec.image,
            "gpuTypeIds": [gpu],
            "gpuCount": 1,
            "cloudType": cloud,
            "computeType": "GPU",
            "containerDiskInGb": int(spec.disk_gb),
            "ports": list(spec.ports),
            "supportPublicIp": True,
            "dockerStartCmd": ["/bin/bash", "-lc", start],
        }
        if spec.max_hours:
            payload["terminateAfter"] = (
                datetime.now(timezone.utc) + timedelta(hours=spec.max_hours)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload.update(spec.extra)
        try:
            created = self._request("POST", "/pods", json=payload)
        except ProviderError as exc:
            if spec.max_hours and "terminateAfter" in str(exc):
                payload.pop("terminateAfter", None)
                created = self._request("POST", "/pods", json=payload)
            else:
                raise
        if not isinstance(created, dict) or not created.get("id"):
            raise ProviderError(
                f"RunPod create pod did not return an id: {created}",
                provider="runpod",
                detail=created,
            )
        return str(created["id"])

    def destroy(self, instance_id: str) -> None:
        self._request("DELETE", f"/pods/{instance_id}")
        self._ssh.pop(instance_id, None)

    def status(self, instance_id: str) -> Instance:
        pod = self._get_pod(instance_id)
        host, port = ssh_from_pod(pod)
        self._ssh[instance_id] = (host, port)
        return instance_from_pod(pod, ssh_is_open(host, port))

    def find(self, label: str) -> Instance | None:
        rows = _as_list(self._request("GET", "/pods"))
        living: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (row.get("name") or "") != label:
                continue
            status = str(row.get("desiredStatus") or "").upper()
            if status in {"TERMINATED", "EXITED"}:
                continue
            living.append(row)
        if not living:
            return None
        pod = living[0]
        pod_id = str(pod.get("id") or "")
        host, port = ssh_from_pod(pod)
        if pod_id:
            self._ssh[pod_id] = (host, port)
        return instance_from_pod(pod, ssh_is_open(host, port))

    def run(self, instance_id: str, command: str) -> str:
        host, port = self._endpoint(instance_id)
        return run_ssh(self._ssh_key(), host, port, "root", command, provider="runpod")

    def upload(self, instance_id: str, local: Path, remote: str) -> None:
        host, port = self._endpoint(instance_id)
        run_scp(self._ssh_key(), host, port, str(local), f"root@{host}:{remote}", provider="runpod")

    def download(self, instance_id: str, remote: str, local: Path) -> None:
        host, port = self._endpoint(instance_id)
        local.parent.mkdir(parents=True, exist_ok=True)
        run_scp(self._ssh_key(), host, port, f"root@{host}:{remote}", str(local), provider="runpod")

    def logs(self, instance_id: str) -> str:
        try:
            raw = self._request("GET", f"/pods/{instance_id}/logs")
        except Exception:
            raw = None
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            for key in ("logs", "output", "stdout", "text"):
                if raw.get(key):
                    return str(raw[key])
        return ""

    def _get_pod(self, instance_id: str) -> dict[str, Any]:
        raw = self._request("GET", f"/pods/{instance_id}", params={"includeMachine": "true"})
        if not isinstance(raw, dict):
            raise NotFound(f"RunPod pod {instance_id} was not found.")
        return raw

    def _endpoint(self, instance_id: str) -> tuple[str, int]:
        cached = self._ssh.get(instance_id)
        if cached and cached[0] and cached[1]:
            return cached[0], cached[1]
        pod = self._get_pod(instance_id)
        host, port = ssh_from_pod(pod)
        self._ssh[instance_id] = (host, port)
        if not host or not port:
            raise SshNotReady("Pod SSH is not published yet.")
        return host, port

    def _ssh_key(self) -> Path:
        key = self.config.ssh_key
        if key is None:
            key = Path.home() / ".runpod" / "ssh" / "runpodctl-ssh-key"
        return key

    def _public_key_line(self, pub_path: Path | None = None) -> str:
        path = Path(pub_path) if pub_path is not None else Path(str(self._ssh_key()) + ".pub")
        if not path.is_file():
            raise AuthError(
                f"RunPod: missing public key at {path}. Add the matching .pub in the RunPod "
                "console (account SSH keys). That is not RUNPOD_SSH_KEY."
            )
        text = path.read_text().strip()
        line = text.splitlines()[0].strip() if text else ""
        if not line or not line.startswith(("ssh-", "ecdsa-", "sk-ssh-", "sk-ecdsa-")):
            raise AuthError(
                f"RunPod: {path} is not an OpenSSH public key. Add the matching .pub in the "
                "RunPod console (account SSH keys)."
            )
        return line

    def ensure_ssh_key(self, pub_path: Path | None = None) -> str:
        """Append the local .pub to the RunPod account. Does not replace existing keys."""
        line = self._public_key_line(pub_path)
        try:
            data = self._graphql("{ myself { pubKey } }")
        except ProviderError as exc:
            raise AuthError(
                "RunPod: could not read account SSH keys. Add the matching .pub in the RunPod "
                "console (account SSH keys). That is not RUNPOD_SSH_KEY."
            ) from exc
        existing = str((data.get("myself") or {}).get("pubKey") or "")
        if _pub_already_present(existing, line):
            return line
        merged = existing.strip()
        merged = f"{merged}\n\n{line}" if merged else line
        try:
            self._graphql(
                "mutation Mutation($input: UpdateUserSettingsInput) { "
                "updateUserSettings(input: $input) { id } }",
                {"input": {"pubKey": merged}},
            )
        except ProviderError as exc:
            raise AuthError(
                "RunPod: could not append the account SSH key. Add the matching .pub in the "
                "RunPod console (account SSH keys). That is not RUNPOD_SSH_KEY."
            ) from exc
        return line


def _pub_already_present(existing: str, line: str) -> bool:
    wanted = line.split()[1] if len(line.split()) > 1 else line.strip()
    for raw in existing.splitlines():
        row = raw.strip()
        if not row:
            continue
        if row == line or (len(row.split()) > 1 and row.split()[1] == wanted):
            return True
    return False


def ensure_ssh_key(cloud: object, pub_path: Path | None = None) -> str:
    """RunPod-only. Not a GpuCloud method."""
    if not isinstance(cloud, RunPodCloud):
        raise AuthError(
            "ensure_ssh_key is RunPod-only. Add the matching .pub in the provider console."
        )
    return cloud.ensure_ssh_key(pub_path=pub_path)
