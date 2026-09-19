from __future__ import annotations

import math
from collections.abc import Sequence

from gpubox._models import Offer


def _finite_or_zero(value: float | None) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return float(value)


def rank_offers(
    offers: Sequence[Offer],
    *,
    price_weight: float = 1.0,
    reliability_weight: float = 0.0,
    disk_weight: float = 0.0,
) -> list[Offer]:
    def score(offer: Offer) -> float:
        price = offer.price_per_hour
        if not math.isfinite(price):
            return math.inf
        return (
            price_weight * price
            - reliability_weight * _finite_or_zero(offer.reliability)
            - disk_weight * _finite_or_zero(offer.disk_space)
        )

    return sorted(offers, key=score)
