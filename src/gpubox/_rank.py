from __future__ import annotations

import math
from collections.abc import Sequence

from gpubox._models import Offer


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
            - reliability_weight * (offer.reliability or 0)
            - disk_weight * (offer.disk_space or 0)
        )

    return sorted(offers, key=score)
