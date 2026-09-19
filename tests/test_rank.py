from __future__ import annotations

import math

from gpubox import FakeCloud, Offer, OfferQuery, connect, rank_offers


def _offer(
    oid: str,
    *,
    price: float,
    reliability: float | None = None,
    disk: float | None = None,
) -> Offer:
    return Offer(
        id=oid,
        gpu_name="RTX_4090",
        price_per_hour=price,
        reliability=reliability,
        disk_space=disk,
    )


def test_rank_offers_exported() -> None:
    assert rank_offers is not None


def test_cheaper_first_by_default() -> None:
    ranked = rank_offers([_offer("dear", price=0.50), _offer("cheap", price=0.20)])
    assert [o.id for o in ranked] == ["cheap", "dear"]


def test_reliability_weight_prefers_higher() -> None:
    ranked = rank_offers(
        [_offer("flaky", price=0.30, reliability=0.4), _offer("solid", price=0.30, reliability=0.9)],
        reliability_weight=1.0,
    )
    assert [o.id for o in ranked] == ["solid", "flaky"]


def test_disk_weight_prefers_more_disk() -> None:
    ranked = rank_offers(
        [_offer("small", price=0.30, disk=40), _offer("big", price=0.30, disk=200)],
        disk_weight=0.01,
    )
    assert [o.id for o in ranked] == ["big", "small"]


def test_missing_reliability_and_disk_count_as_zero() -> None:
    ranked = rank_offers(
        [_offer("bare", price=0.30), _offer("known", price=0.30, reliability=0.8, disk=100)],
        reliability_weight=1.0,
        disk_weight=0.01,
    )
    assert [o.id for o in ranked] == ["known", "bare"]


def test_non_finite_price_sorts_last() -> None:
    ranked = rank_offers(
        [
            _offer("nan", price=math.nan),
            _offer("ok", price=0.40),
            _offer("inf", price=math.inf),
        ]
    )
    assert ranked[0].id == "ok"
    assert {ranked[1].id, ranked[2].id} == {"nan", "inf"}


def test_stable_when_scores_equal() -> None:
    first = _offer("a", price=0.30)
    second = _offer("b", price=0.30)
    ranked = rank_offers([first, second])
    assert [o.id for o in ranked] == ["a", "b"]


def test_rank_fakecloud_offers() -> None:
    cloud = connect("fake")
    assert isinstance(cloud, FakeCloud)
    ranked = rank_offers(cloud.list_offers(OfferQuery(gpu_names=["RTX_4090"])))
    assert ranked[0].id == "101"
    assert ranked[0].price_per_hour == 0.32
