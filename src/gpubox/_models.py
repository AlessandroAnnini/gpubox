from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field


def _as_str_id(value: Any) -> Any:
    if value is None:
        return None
    return str(value)


StrId = Annotated[str, BeforeValidator(_as_str_id)]
OptStrId = Annotated[str | None, BeforeValidator(_as_str_id)]


@dataclass
class ClientConfig:
    api_key: str
    ssh_key: Path | None = None
    timeout: float = 30.0


@dataclass
class LaunchSpec:
    image: str
    disk_gb: int = 50
    label: str = "gpubox"
    ssh: bool = True
    start_command: str | None = None
    ports: list[str] = field(default_factory=lambda: ["22/tcp"])
    max_hours: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OfferQuery:
    gpu_names: list[str] | None = None
    min_disk_gb: float | None = None
    exclude_hosts: Sequence[str] = ()
    limit: int = 12
    raw: str | None = None


class Account(BaseModel):
    username: str | None = None
    email: str | None = None
    credit: float = 0
    connected: bool = True


class Offer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: StrId
    gpu_name: str
    gpu_ram: float | None = None
    num_gpus: int = 1
    cpu_ram: float | None = None
    disk_space: float | None = None
    price_per_hour: float = Field(
        validation_alias=AliasChoices("price_per_hour", "dph_total"),
    )
    geolocation: str | None = None
    reliability: float | None = None
    inet_up: float | None = None
    inet_down: float | None = None
    machine_id: int | None = None
    host_id: int | None = None

    @property
    def dph_total(self) -> float:
        return self.price_per_hour


class Instance(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: OptStrId = None
    provider_status: str | None = None
    gpu_name: str | None = None
    price_per_hour: float | None = Field(
        default=None,
        validation_alias=AliasChoices("price_per_hour", "dph_total"),
    )
    geolocation: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_open: bool = False
    host_id: int | None = None
    machine_id: int | None = None
    label: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def dph_total(self) -> float | None:
        return self.price_per_hour
