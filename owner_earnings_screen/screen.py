"""Join the universe to fundamentals, classify every company, value the ones
the framework applies to."""
import math
import re

import numpy as np
import pandas as pd

from . import config as C
from . import panel as P
from . import sec, universe
from . import valuation as V

STALE_BEFORE = pd.Timestamp("2025-08-01")   # latest annual report older than this


# ---- per-company history ---------------------------------------------------
def _fiscal_years(g):
    """Rows that are real fiscal years.

    Some filers also tag trailing-twelve-month figures in their 10-Qs, which
    land in the same annual frames. Keep rows ending in the company's usual
    fiscal-year month, inferred from its own history (the fiscal-year-end
    field in the SEC's submissions data is too often wrong to use).
    """
    g = g[g["ni"].notna() & g["fy_end"].notna()]
    if g.empty:
        return g
    month = g["fy_end"].dt.month.mode().iloc[-1]      # ties: the later month
    diff = (g["fy_end"].dt.month - month) % 12
    return g[(diff <= 1) | (diff == 11)]


def _sum(a):
    return float(np.nansum(a)) if np.isfinite(a).any() else math.nan


def _div(a, b):
    return a / b if (b is not None and np.isfinite(b) and b != 0
                     and a is not None and np.isfinite(a)) else math.nan


def normalise_earnings(g):
    """Per-year net income attributable to shareholders, and their share of the group.

    A year's net income is capped at 85% of pre-tax income from continuing
    operations, which strips tax windfalls and gains on discontinued
    businesses. The cap only ever lowers reported income.
    """
    total = g["ni_total"].where(g["ni_total"] > 0)
    share = (g["ni"] / total).clip(0, 1).fillna(1.0)
    cap = (1 - C.MIN_TAX) * g["pretax"] * share
    return g["ni"].where(cap.isna() | (g["ni"] <= cap), cap), share


def fill_cash_items(g, cur, ni_adj):
    """D&A and capex with gaps filled, plus a note on what was assumed.

    Filers that use their own line items leave gaps in the standard tags.
    - D&A missing: taken as zero, which understates owner earnings.
    - capex missing in some years: the average of the reported years.
    - capex never reported: assumed equal to D&A when D&A is under 15% of net
      income (asset-light); otherwise left missing, and the company is not valued.
    """
    notes = []
    da = g["da"].fillna(g.loc[cur, "da"].mean())
    if da.isna().any():
        da = da.fillna(0.0)
        notes.append("da_missing")
    capex = g["capex"].fillna(g.loc[cur, "capex"].mean())
    if capex.isna().any():
        if da[cur].mean() < 0.15 * ni_adj[cur].mean():
            capex = capex.fillna(da)
            notes.append("capex_assumed")
    return da, capex, notes


def company_metrics(g):
    """Owner earnings, quality measures and the inputs to the four steps for one company."""
    g = _fiscal_years(g)
    if g.empty:
        return None
    g = g.copy()
    last_cy = int(g["cy"].iloc[-1])
    cur = g["cy"] > last_cy - C.AVG_YEARS            # "current" window
    g["ni_adj"], share = normalise_earnings(g)
    g["da"], g["capex"], notes = fill_cash_items(g, cur, g["ni_adj"])
    # D&A and capex are consolidated at 100%; scale them to the parent's share
    g["oe"] = g["ni_adj"] + share * (g["da"] - g["capex"])
    w = g[g["cy"] > last_cy - C.HIST_YEARS]          # quality window
    c = g[cur]
    out = {"fy_end": g["fy_end"].iloc[-1], "n_years": len(w), "n_avg": len(c),
           "data_notes": " ".join(notes)}

    out["ni_reported"] = c["ni"].mean()
    out["ni"] = c["ni_adj"].mean()
    out["da"] = c["da"].mean()
    out["capex"] = c["capex"].mean()
    out["oe"] = c["oe"].mean() if c["oe"].notna().all() else math.nan
    out["fcf_ex_sbc"] = (c["cfo"] - c["capex"] - c["sbc"].fillna(0)).mean()
    out["rev"] = c["rev"].mean()
    out["premium_share"] = _div(c["premiums"].mean(), out["rev"])
    # net income can only be trusted where revenue and a pre-tax or operating
    # profit line exist to check it against
    out["verifiable"] = bool(c["rev"].notna().any()
                             and c["pretax"].fillna(c["opinc"]).notna().any())
    out["equity"] = g["equity"].iloc[-1]
    out["assets"] = g["assets"].iloc[-1]
    out["shares"] = g["shares"].dropna().iloc[-1] if g["shares"].notna().any() else math.nan

    # margins: pre-tax, else operating, else net
    profit = w["pretax"].fillna(w["opinc"]).fillna(w["ni"])
    margin = (profit / w["rev"]).replace([np.inf, -np.inf], np.nan)
    cur_margin = margin[w["cy"] > last_cy - C.AVG_YEARS].mean()
    out["margin_now"] = cur_margin
    out["margin_norm"] = margin.median() if margin.notna().sum() >= C.MIN_HIST_YEARS else math.nan
    out["margin_min"] = margin.min()
    out["margin_ratio"] = V.margin_ratio(out["margin_norm"], cur_margin)

    # quality
    eq_avg = (w["equity"] + w["equity"].shift(1).fillna(w["equity"])) / 2
    roe = (w["ni"] / eq_avg).where(eq_avg > 0)
    out["roe_med"] = roe.median()
    out["roa_med"] = (w["ni"] / w["assets"]).median()
    out["ni_pos_years"] = int((w["ni"] > 0).sum())
    ni_sum = _sum(w["ni_total"].fillna(w["ni"]))     # consolidated, to match cash flow
    out["cash_conv"] = _div(_sum(w["cfo"]), ni_sum) if ni_sum > 0 else math.nan
    out["fcf_conv"] = _div(_sum(w["cfo"] - w["capex"]), ni_sum) if ni_sum > 0 else math.nan
    out["capex_to_da"] = _div(_sum(w["capex"]), _sum(w["da"]))
    out["capex_to_rev"] = _div(_sum(w["capex"]), _sum(w["rev"]))
    out["capex_to_ni"] = _div(_sum(w["capex"]), ni_sum) if ni_sum > 0 else math.nan
    out["payout"] = _div(_sum(w["div"].fillna(0) + w["buyback"].fillna(0)), ni_sum) \
        if ni_sum > 0 else math.nan
    out["rnd_to_rev"] = _div(c["rnd"].mean(), out["rev"])
    rev = w["rev"].dropna()
    out["rev_cagr"] = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev) - 1)) - 1
                       if len(rev) >= 3 and rev.iloc[0] > 0 and rev.iloc[-1] > 0 else math.nan)
    n3 = min(3, len(w) // 2)
    out["ni_grew"] = bool(n3 and w["ni"].iloc[-n3:].mean() > w["ni"].iloc[:n3].mean())
    interest = c["interest"].mean()
    out["int_cover"] = _div(profit[w["cy"] > last_cy - C.AVG_YEARS].mean() + interest, interest) \
        if interest and interest > 0 else math.nan
    out["eq_to_assets"] = _div(out["equity"], out["assets"])
    return out


def is_franchise(m, cyclical):
    """Step 3 proxy for pricing power: a decade of high, stable, cash-backed returns."""
    high_return = (m["roe_med"] >= 0.15) or (not (m["equity"] > 0) and m["roa_med"] >= 0.08)
    stable = (np.isfinite(m["margin_norm"]) and m["margin_norm"] > 0
              and m["margin_min"] >= 0.5 * m["margin_norm"])
    return bool(m["n_years"] >= 8 and m["ni_pos_years"] == m["n_years"] and high_return
                and stable and m["fcf_conv"] >= 0.6 and not cyclical)


def is_sees_like(m):
    """High returns, little capital needed, most earnings paid out, still growing."""
    return bool(m["roe_med"] >= 0.20 and m["capex_to_ni"] <= 0.4
                and m["payout"] >= 0.7 and m["ni_grew"]
                and m["n_years"] >= 8 and m["ni_pos_years"] == m["n_years"])


# ---- universe --------------------------------------------------------------
_SECURITY = re.compile(r"\b(common (stock|shares)|ordinary shares|class [a-z]\b.*|"
                       r"american depositary .*|\(.*?\))", re.I)
_SUFFIX = re.compile(r"\b(the|inc|incorporated|corp|corporation|company|co|holdings?|"
                     r"ltd|limited|plc|group|new|de)\b", re.I)


def _name_key(name):
    """Company name reduced to its distinctive letters, for matching across sources."""
    name = _SUFFIX.sub(" ", _SECURITY.sub(" ", name))
    return re.sub(r"[^a-z0-9]", "", name.lower())


def build_universe(pan, subs, size=C.UNIVERSE_SIZE):
    """Top `size` US-listed companies by market cap, one row per company."""
    u = universe.load()
    recent = pan[pan["cy"] >= 2024].groupby("cik")["assets"].max()
    t2c = {}
    for cik, s in subs.items():
        for t in s.get("tickers", []):
            t = universe.norm_ticker(t)
            if t not in t2c or recent.get(cik, 0) > recent.get(t2c[t], 0):
                t2c[t] = cik
    u["cik"] = u["ticker"].map(t2c)
    # A reorganised company (new holding company, new registrant) lists under a
    # registrant with no history while the filings sit with the old one, which
    # no longer carries a ticker. Match those by name.
    orphans = {}
    for cik, s in subs.items():
        if not s.get("tickers") and cik in recent.index:
            orphans.setdefault(_name_key(s.get("name") or ""), []).append(cik)
    by_name = u["name"].map(_name_key).map(
        lambda k: orphans[k][0] if len(k) >= 6 and len(orphans.get(k, [])) == 1 else None)
    u["matched_by_name"] = u["cik"].isna() & by_name.notna()
    u["cik"] = u["cik"].fillna(by_name).astype("Int64")

    # market cap missing in the listing: price x diluted shares from the filings
    shares = pan.dropna(subset=["shares"]).groupby("cik")["shares"].last()
    shares = shares[shares >= 1e6]          # smaller counts are tagged in thousands or millions
    est = u["price"] * u["cik"].map(shares).astype(float)
    u["mc_estimated"] = ~(u["mktcap"] > 0) & (est > 0)
    u["mktcap"] = u["mktcap"].where(u["mktcap"] > 0, est)
    u = u[u["mktcap"] > 0].sort_values("mktcap", ascending=False)

    # one row per company: share classes collapse onto the largest listing
    key = u["cik"].astype("string").fillna("T:" + u["ticker"])
    u["tickers"] = u.groupby(key)["ticker"].transform(lambda s: " ".join(s))
    u = u[~key.duplicated()].head(size).reset_index(drop=True)
    u.insert(0, "rank", u.index + 1)
    return u


def classify(row, m, sub):
    """Bucket deciding whether the owner-earnings framework applies as-is."""
    sic = (sub or {}).get("sic")
    if m is None:
        if pd.isna(row["cik"]):
            return "foreign" if row["country"] not in ("United States", "") else "no_data"
        return "no_data"
    if sic in C.SIC_FUND:
        return "fund"
    if sic in C.SIC_FINANCIAL or m["premium_share"] >= C.INSURER_PREMIUM_SHARE:
        return "financial"
    if sic in C.SIC_REIT or "Real Estate Investment Trust" in (row["industry"] or ""):
        return "reit"
    if m["fy_end"] < STALE_BEFORE:
        return "stale"
    if m["n_years"] < C.MIN_HIST_YEARS:
        return "short_history"
    if not m["ni"] > 0:
        return "loss_making"
    if not np.isfinite(m["oe"]) or not m["verifiable"]:
        return "data_gap"
    if m["oe"] <= 0:
        # with D&A unknown (taken as zero) a negative figure proves nothing
        return "data_gap" if "da_missing" in m["data_notes"] else "cash_burn"
    return "valued"


def run(rate=C.RISK_FREE, size=C.UNIVERSE_SIZE):
    pan = P.load()
    subs = sec.load_submissions()
    u = build_universe(pan, subs, size)
    groups = dict(tuple(pan[pan["cik"].isin(u["cik"].dropna().astype(int))].groupby("cik")))

    rows = []
    for _, r in u.iterrows():
        cik = None if pd.isna(r["cik"]) else int(r["cik"])
        sub = subs.get(cik)
        m = company_metrics(groups[cik]) if cik in groups else None
        rec = r.to_dict()
        rec.update(sic=(sub or {}).get("sic"), sic_desc=(sub or {}).get("sic_desc"),
                   annual_form=(sub or {}).get("annual_form"))
        rec["bucket"] = classify(r, m, sub)
        if m is not None:
            rec.update(m)
            cyc = (rec["sic"] in C.SIC_CYCLICAL) or (r["sector"] in C.NASDAQ_CYCLICAL_SECTORS)
            rec["cyclical"] = bool(cyc)
            rec["franchise"] = is_franchise(m, cyc)
            rec["sees_like"] = is_sees_like(m)
            mc = r["mktcap"]
            rec["foreign"] = r["country"] not in ("United States", "")
            rec["one_off"] = bool(m["ni"] < 0.8 * m["ni_reported"])
            rec["mc_check"] = _div(mc, r["price"] * m["shares"])
            # listing market cap far from price x shares in the last annual report:
            # a merger, spin-off or split since then (above 20x is a share-scale artefact)
            rec["share_mismatch"] = bool(not rec["foreign"] and rec["mc_check"] < 20
                                         and not 0.7 <= rec["mc_check"] <= 1.4)
            rec["earn_yield"] = m["ni"] / mc
            rec["suspect"] = bool(rec["earn_yield"] > 0.5)      # a P/E under 2 is a data error
            rec["oe_yield"] = _div(m["oe"], mc)
            rec["fcf_yield"] = _div(m["fcf_ex_sbc"], mc)
            rec["pb"] = _div(mc, m["equity"]) if m["equity"] > 0 else math.nan
            if rec["bucket"] == "valued":
                v = V.four_steps(m["oe"], m["ni"], rate, rec["franchise"], m["margin_ratio"])
                rec.update(v)
                rec["pv_low"] = mc / v["v_low"]
                rec["pv_high"] = mc / v["v_high"]
                rec["mos"] = 1 - rec["pv_low"]
                rec["implied_g"] = V.implied_growth(v["v_low"] * rate, mc, rate)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["cik"] = df["cik"].astype("Int64")
    return df


def is_clean(df):
    """No sign that the filings describe a different company than the one trading."""
    return ((df["bucket"] == "valued") & ~_flag(df, "share_mismatch") & ~_flag(df, "suspect"))


def passes_quality(df):
    """Gates applied before a cheap stock is listed as a candidate."""
    full_record = df["ni_pos_years"] >= np.minimum(df["n_years"], 8)
    return (is_clean(df) & (df["n_years"] >= 7) & full_record
            & (df["fcf_conv"] >= 0.5) & ~(df["int_cover"] < 3))


def _flag(df, col):
    return df[col].fillna(False).astype(bool)
