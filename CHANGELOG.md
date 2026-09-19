# Changelog

All notable changes to this project are documented here.

## [0.7.3] - 2026-09-19

### Changed

- README is caller-first: hero, one example, honest provider lines, errors.
- `MemoryCloud` and `StudioCloud` are no longer exported from `gpubox`. Use `FakeCloud` and `GpuCloud`.

### Fixed

- RunPod HTTP 500 with no capacity is `Unavailable`.
- Vast create, execute, and destroy raise `ProviderError` instead of leaking vendor exceptions.
- `gpubox rent` returns 1 and still destroys if SSH or the command fails.
- CLI accepts `--ssh-key`, `RUNPOD_SSH_KEY` / `LAMBDA_SSH_KEY`, and `--raw`.
- README hero is a PNG. GitHub's image proxy strips SVG `<text>`, so the wordmark vanished.

## [0.7.2] - 2026-09-19

- Documented the 2026-09-19 RunPod RTX A4000 live receipt at $0.17/hr.

## [0.7.1] - 2026-09-19

- Opt-in live tests (`GPUBOX_LIVE=1`) that snapshot ids and destroy only boxes we create.

## [0.7.0] - 2026-09-19

- Added the `gpubox` CLI: list, list --rank, rent, status, destroy.

## [0.6.1] - 2026-09-19

- Public author is Alessandro Annini. MIT copyright matches.

## [0.6.0] - 2026-09-19

- `rank_offers` is arithmetic on one provider list. It is not a Protocol method.

## [0.5.1] - 2026-09-19

- Install from `git+https://github.com/AlessandroAnnini/gpubox`. PyPI waits on purpose.

## [0.5.0] - 2026-09-19

- First `rank_offers` sort: cheaper first; non-finite price last.

## [0.4.0] - 2026-09-19

- Pinned the public API from `VERSION` (hatch reads the same file).

## [0.3.0] - 2026-09-19

- Lambda Labs adapter. Offer ids are `instance_type|region`.

## [0.2.0] - 2026-09-19

- Caller docs: connect, extras, errors, caller owns the job.

## [0.1.0] - 2026-09-19

- `GpuCloud` Protocol, `connect()`, `FakeCloud`, Vast and RunPod adapters.
