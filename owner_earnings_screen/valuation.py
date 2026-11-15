"""The four-step owner-earnings valuation, as pure functions.

Buffett's 1973 Washington Post arithmetic (as retold by Hagstrom):
  1. owner earnings = net income + D&A - capital expenditure, capitalised at
     the long Treasury yield                           10.4 / 6.81%  = $150m
  2. assume capex ~ D&A over time, so owner earnings ~ net income
                                                       13.3 / 6.81%  = $196m
  3. pricing power: capitalise 3 points lower           13.3 / 3.81%  = $350m
  4. margins back to their historical average           -> up to     $485m
against a market price of about $80m.
"""
import math

from . import config as C


def owner_earnings(ni, da, capex):
    """Step 1 cash flow. Every dollar of capex is treated as maintenance."""
    return ni + da - capex


def capitalise(cash_flow, rate):
    """Value of a level perpetuity: cash flow divided by the yield."""
    return cash_flow / rate


def franchise_cap_rate(rate, growth=C.GROWTH_ADJ, floor=C.MIN_CAP_RATE):
    """Step 3 capitalisation rate.

    Subtracting 3 points from 6.81% took the Post from 14.7x to 26x. Applied to
    a 4-5% yield the same subtraction gives 50-80x, so the rate is floored at
    the 3.81% Buffett actually used.
    """
    return max(rate - growth, floor)


def margin_ratio(normal_margin, current_margin, clip=C.MARGIN_RATIO_CLIP):
    """Step 4 multiplier: historical-normal margin over the current margin.

    Symmetric: a business earning above its normal margin is marked down,
    which is what keeps cyclicals at peak earnings from looking cheap.
    """
    if not (_ok(normal_margin) and _ok(current_margin)) or current_margin <= 0 \
            or normal_margin <= 0:
        return math.nan
    return min(max(normal_margin / current_margin, clip[0]), clip[1])


def four_steps(oe, ni, rate, franchise=False, ratio=math.nan):
    """Return the four step values plus the conservative and optimistic ends.

    v_low never uses growth and only ever marks margins down, so the margin of
    safety is measured against a no-growth, no-recovery value.
    """
    v1 = capitalise(oe, rate)
    v2 = capitalise(ni, rate)
    v3 = capitalise(ni, franchise_cap_rate(rate)) if franchise else v2
    v4 = v3 * ratio if _ok(ratio) else v3
    down = min(ratio, 1.0) if _ok(ratio) else 1.0
    v_low = min(v1, v2, v2 * down)
    v_high = max(v1, v2, v3, v4)
    return {"v1": v1, "v2": v2, "v3": v3, "v4": v4, "v_low": v_low, "v_high": v_high}


def implied_growth(cash_flow, price, rate):
    """Perpetual growth the price needs at the risk-free rate: g = r - CF/P.

    Negative means the price is below the no-growth value.
    """
    return rate - cash_flow / price


def _ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))
