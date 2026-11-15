"""Assemble cached frames into one row per company per fiscal year."""
import pandas as pd

from . import config as C
from . import sec

PATH = C.DATA_DIR / "panel.pkl"


def _concept(tags, periods, largest=False):
    """Long table (cik, period, end, val), one value per company and period.

    By default the first tag in `tags` that reports wins; with `largest`, the
    biggest value does (see config.LARGEST_OF).
    """
    parts = []
    for rank, tag in enumerate(tags):
        for p in periods:
            rows = sec.load_frame(tag, p)
            if rows:
                d = pd.DataFrame(rows, columns=["cik", "start", "end", "val"])
                d["period"], d["rank"] = p, rank
                parts.append(d[["cik", "period", "end", "val", "rank"]])
    if not parts:
        return pd.DataFrame(columns=["cik", "period", "end", "val"])
    d = pd.concat(parts, ignore_index=True)
    d = d.sort_values("val", ascending=False) if largest else d.sort_values("rank")
    return d.drop_duplicates(["cik", "period"]).drop(columns="rank")


def repair_scale(x, refs):
    """Fix values reported in thousands or millions without the scale.

    Pay-versus-performance tables in proxy statements re-tag net income, often
    with the wrong scale, and the frames API serves the latest-filed fact. A
    value is rescaled when 10^3 or 10^6 brings it in line with a reference
    figure for the same year (consolidated profit, profit to common, pre-tax).
    """
    out = x.copy()
    fixed = pd.Series(False, index=x.index)
    for ref in refs:
        for k in (1e3, 1e6, 1e-3, 1e-6):
            hit = ~fixed & (out / ref * k).between(0.2, 1.5)
            out = out.where(~hit, out * k)
            fixed |= hit
    return out, fixed


def build():
    years = range(C.FIRST_YEAR, C.LAST_YEAR + 1)
    annual = [f"CY{y}" for y in years]
    quarter_ends = [f"CY{y}Q{q}I" for y in years for q in (1, 2, 3, 4)]

    cols, ends = {}, []
    for key, tags in {**C.DURATION_TAGS, **C.SHARE_TAGS}.items():
        d = _concept(tags, annual, largest=(key in C.LARGEST_OF))
        cols[key] = d.set_index(["cik", "period"])["val"]
        if key in ("ni_parent", "ni_total", "cfo", "rev"):
            ends.append(d.set_index(["cik", "period"])["end"])
    panel = pd.DataFrame(cols)
    # fiscal-year end date, from whichever core statement line is present
    fy_end = ends[0]
    for e in ends[1:]:
        fy_end = fy_end.combine_first(e)
    panel["fy_end"] = pd.to_datetime(fy_end.reindex(panel.index))
    panel = panel.reset_index()
    panel["cy"] = panel["period"].str[2:].astype(int)

    # balance-sheet items are instants: match them on the fiscal-year end date
    for key, tags in C.INSTANT_TAGS.items():
        d = _concept(tags, quarter_ends)
        d["fy_end"] = pd.to_datetime(d["end"])
        d = d.sort_values("fy_end").drop_duplicates(["cik", "fy_end"], keep="last")
        d = d[["cik", "fy_end", "val"]].rename(columns={"val": key})
        d = d.astype({"cik": "int64"})
        have = panel.dropna(subset=["fy_end"]).sort_values("fy_end")
        m = pd.merge_asof(have[["cik", "cy", "fy_end"]], d.sort_values("fy_end"),
                          on="fy_end", by="cik", direction="nearest",
                          tolerance=pd.Timedelta(days=10))
        panel = panel.merge(m[["cik", "cy", key]], on=["cik", "cy"], how="left")

    # Net income to common shareholders. The frames API serves the latest-filed
    # fact, and proxy statements re-tag net income with the wrong scale or on a
    # consolidated basis, so take the lowest of three readings of the same
    # figure: as tagged, available to common, and consolidated less minorities.
    refs = [panel["ni_total"], panel["pretax"]]
    parent, fixed_p = repair_scale(panel["ni_parent"], refs + [panel["ni_common"]])
    common, fixed_c = repair_scale(panel["ni_common"], refs + [parent])
    ex_minorities = panel["ni_total"] - panel["nci"]
    panel["ni"] = pd.concat([parent, common, ex_minorities], axis=1).min(axis=1) \
        .fillna(panel["ni_total"])
    panel["ni_rescaled"] = fixed_p | fixed_c

    # D&A: the larger of the combined tag and depreciation plus amortisation
    split = panel["dep"] + panel["amort"].fillna(0)
    panel["da"] = pd.concat([panel["da"], split], axis=1).max(axis=1)
    # capex: plant and equipment plus capitalised software and purchased intangibles
    panel["capex"] = panel[["capex", "capsw", "capint"]].sum(axis=1, min_count=1)
    panel = panel.drop(columns=["dep", "amort", "capsw", "capint", "period",
                                "ni_parent", "ni_common", "nci"])
    panel = panel.sort_values(["cik", "cy"]).reset_index(drop=True)
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_pickle(PATH)
    return panel


def load():
    return pd.read_pickle(PATH)
