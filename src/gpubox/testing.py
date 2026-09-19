from __future__ import annotations

from pathlib import Path

from gpubox._models import Account, Instance, LaunchSpec, Offer, OfferQuery


class FakeCloud:
    """In-memory GpuCloud. Default tests use this. Never rents a GPU."""

    def __init__(self) -> None:
        self.created = False
        self.destroyed = False
        self.copies: list[tuple[str, str]] = []
        self.commands: list[str] = []
        self._instance_id = "77"
        self._label = "gpubox"
        self._log = "container running\n"
        self._status = "running"

    def account(self) -> Account:
        return Account(username="tester", email="test@local", credit=12.5, connected=True)

    def list_offers(self, query: OfferQuery | None = None) -> list[Offer]:
        del query
        return [
            Offer(
                id="101",
                gpu_name="RTX_4090",
                gpu_ram=24,
                price_per_hour=0.32,
                geolocation="Iceland",
            )
        ]

    def create(self, offer_id: str, spec: LaunchSpec) -> str:
        del offer_id
        self.created = True
        self.destroyed = False
        self._label = spec.label
        self._status = "running"
        return self._instance_id

    def destroy(self, instance_id: str) -> None:
        del instance_id
        self.destroyed = True
        self.created = False

    def status(self, instance_id: str) -> Instance:
        if not self.created:
            return Instance(id=None, provider_status=None, ssh_open=False)
        return Instance(
            id=instance_id or self._instance_id,
            provider_status=self._status,
            gpu_name="RTX_4090",
            price_per_hour=0.32,
            geolocation="Iceland",
            ssh_host="ssh.example",
            ssh_port=22,
            ssh_open=True,
            label=self._label,
        )

    def find(self, label: str) -> Instance | None:
        if not self.created or label != self._label:
            return None
        return self.status(self._instance_id)

    def run(self, instance_id: str, command: str) -> str:
        del instance_id
        self.commands.append(command)
        return "ok"

    def upload(self, instance_id: str, local: Path, remote: str) -> None:
        del instance_id
        self.copies.append((str(local), remote))

    def download(self, instance_id: str, remote: str, local: Path) -> None:
        del instance_id
        self.copies.append((remote, str(local)))
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(b"ply" * 80)

    def logs(self, instance_id: str) -> str:
        del instance_id
        return self._log


MemoryCloud = FakeCloud
