from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from gpubox._errors import GpuBoxError
from gpubox._factory import connect
from gpubox._models import LaunchSpec, OfferQuery
from gpubox._rank import rank_offers
from gpubox._ssh import wait_until_ssh

_ENV_KEYS = {
    "vast": "VAST_API_KEY",
    "vastai": "VAST_API_KEY",
    "runpod": "RUNPOD_API_KEY",
    "lambda": "LAMBDA_API_KEY",
    "lambdalabs": "LAMBDA_API_KEY",
}
_ENV_SSH = {
    "runpod": "RUNPOD_SSH_KEY",
    "lambda": "LAMBDA_SSH_KEY",
    "lambdalabs": "LAMBDA_SSH_KEY",
}


def _api_key(provider: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    env = _ENV_KEYS.get(provider.strip().lower())
    if env:
        return os.environ.get(env, "")
    return ""


def _ssh_key(args: argparse.Namespace) -> str | None:
    explicit = getattr(args, "ssh_key", None)
    if explicit:
        return str(explicit)
    env = _ENV_SSH.get(args.provider.strip().lower())
    if env:
        return os.environ.get(env) or None
    return None


def _connect(args: argparse.Namespace):
    ssh_key = _ssh_key(args)
    if ssh_key:
        return connect(args.provider, api_key=_api_key(args.provider, args.api_key), ssh_key=ssh_key)
    return connect(args.provider, api_key=_api_key(args.provider, args.api_key))


def _query(args: argparse.Namespace) -> OfferQuery:
    gpus = list(args.gpu) if getattr(args, "gpu", None) else None
    raw = getattr(args, "raw", None)
    return OfferQuery(gpu_names=gpus, limit=int(getattr(args, "limit", 12)), raw=raw)


def _print_offers(offers: Sequence) -> None:
    for offer in offers:
        print(f"{offer.id}\t{offer.gpu_name}\t{offer.price_per_hour}")


def cmd_list(args: argparse.Namespace) -> int:
    cloud = _connect(args)
    offers = cloud.list_offers(_query(args))
    if args.rank:
        offers = rank_offers(offers)
    _print_offers(offers)
    return 0


def cmd_rent(args: argparse.Namespace) -> int:
    cloud = _connect(args)
    offers = rank_offers(cloud.list_offers(_query(args)))
    if not offers:
        print("no offers", file=sys.stderr)
        return 1
    spec = LaunchSpec(image=args.image, disk_gb=args.disk_gb, label=args.label)
    box = None
    rc = 1
    try:
        box = cloud.create(offers[0].id, spec)
        wait_until_ssh(cloud, box, timeout=args.timeout)
        print(cloud.run(box, args.cmd), end="")
        rc = 0
    except GpuBoxError as exc:
        print(exc, file=sys.stderr)
        rc = 1
    finally:
        if box:
            try:
                cloud.destroy(box)
            except GpuBoxError as exc:
                print(exc, file=sys.stderr)
                rc = 1
    return rc


def cmd_status(args: argparse.Namespace) -> int:
    inst = _connect(args).status(args.id)
    print(f"{inst.id}\t{inst.provider_status}\tssh_open={inst.ssh_open}")
    return 0


def cmd_destroy(args: argparse.Namespace) -> int:
    _connect(args).destroy(args.id)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpubox")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-p", "--provider", required=True)
    common.add_argument("--api-key", default=None)
    common.add_argument("--ssh-key", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", parents=[common])
    p_list.add_argument("--gpu", action="append")
    p_list.add_argument("--rank", action="store_true")
    p_list.add_argument("--limit", type=int, default=12)
    p_list.add_argument("--raw", default=None)
    p_list.set_defaults(func=cmd_list)

    p_rent = sub.add_parser("rent", parents=[common])
    p_rent.add_argument("--gpu", action="append")
    p_rent.add_argument("--cmd", default="nvidia-smi")
    p_rent.add_argument("--image", default="ubuntu:22.04")
    p_rent.add_argument("--disk-gb", type=int, default=16)
    p_rent.add_argument("--label", default="gpubox")
    p_rent.add_argument("--limit", type=int, default=12)
    p_rent.add_argument("--timeout", type=float, default=300)
    p_rent.add_argument("--raw", default=None)
    p_rent.set_defaults(func=cmd_rent)

    p_status = sub.add_parser("status", parents=[common])
    p_status.add_argument("id")
    p_status.set_defaults(func=cmd_status)

    p_destroy = sub.add_parser("destroy", parents=[common])
    p_destroy.add_argument("id")
    p_destroy.set_defaults(func=cmd_destroy)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except GpuBoxError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
