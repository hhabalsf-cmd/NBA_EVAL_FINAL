"""Single source of truth for PRA reconciliation and uncertainty.

Root cause fixed here (2026-07 audit): PRA was defined three different
ways across code paths — an 85/15 blend in ``MLPredictor.predict()`` but a
pure component sum in the injury-boost and blowout-discount paths — and
its serve-time std came from the *independent* PRA model's quantile
spread while the served value was the blend. PRA errors compound three
stats (graded MAE ~13 vs ~6.5 for PTS), so the understated std pushed
``prob_over`` into the overconfident tail (all 8 graded PRA picks landed
at prob 74-84; the >=80 ones went 0-4).

Every PRA producer/consumer should go through these helpers.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Optional

# Weight of the component sum in the PRA blend. The independent PRA model
# gets the remainder — it sees PRA-specific signal but compounds errors,
# so it is heavily down-weighted.
PRA_COMPONENT_WEIGHT = 0.85

COMPONENT_STATS = ('PTS', 'REB', 'AST')


def reconcile_pra(predictions: Mapping[str, float]) -> dict:
    """Return a new predictions dict with PRA consistent with its components.

    PRA = 0.85 x (PTS + REB + AST) + 0.15 x independent PRA prediction.
    When no independent PRA value is present, PRA is the pure component sum.
    When any component is missing, the dict is returned unchanged (copy).
    """
    result = dict(predictions)
    if not all(s in result for s in COMPONENT_STATS):
        return result

    component_sum = sum(result[s] for s in COMPONENT_STATS)
    independent = result.get('PRA')
    if independent is None:
        result['PRA'] = component_sum
    else:
        result['PRA'] = (
            PRA_COMPONENT_WEIGHT * component_sum
            + (1 - PRA_COMPONENT_WEIGHT) * independent
        )
    return result


def rescale_pra_with_components(
    before: Mapping[str, float], after: Mapping[str, float]
) -> dict:
    """Re-blend PRA after component predictions were adjusted.

    The independent PRA share is scaled by the same aggregate ratio the
    component sum changed by (injury boost, blowout discount, ...), then
    the standard 85/15 blend is applied. Without this, PRA would retain
    15% of its *unadjusted* value and drift away from its components in
    exactly the games where adjustments fire.

    Returns a new dict based on ``after``. Falls back to plain
    ``reconcile_pra`` when the ratio is undefined (missing components or
    zero pre-adjustment sum).
    """
    result = dict(after)
    if not all(s in before and s in result for s in COMPONENT_STATS):
        return reconcile_pra(result)

    old_sum = sum(before[s] for s in COMPONENT_STATS)
    if old_sum <= 0:
        return reconcile_pra(result)

    independent = result.get('PRA')
    if independent is not None:
        new_sum = sum(result[s] for s in COMPONENT_STATS)
        result['PRA'] = independent * (new_sum / old_sum)
    return reconcile_pra(result)


def pra_std_floor(pra_std: float, component_stds: Iterable[Optional[float]]) -> float:
    """Floor PRA's std at the RSS of its components' stds.

    PTS/REB/AST errors are positively correlated (minutes drive all
    three), so the true PRA error std is at least
    sqrt(std_PTS^2 + std_REB^2 + std_AST^2) — the independent-errors
    lower bound. A PRA std below that is understated and produces
    overconfident probabilities.

    Missing (None) component stds are skipped; with no components known,
    ``pra_std`` is returned unchanged.
    """
    known = [s for s in component_stds if s is not None]
    if not known:
        return pra_std
    rss = math.sqrt(sum(s * s for s in known))
    return max(pra_std, rss)
