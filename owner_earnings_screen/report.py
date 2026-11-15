"""Render the screen as a Markdown report (in Chinese, for the reader of the framework)."""
import numpy as np
import pandas as pd

from . import config as C
from .screen import is_clean, passes_quality

BUCKETS = [
    ("valued", "可直接估值", "四步法适用，已算出估值区间"),
    ("cash_burn", "利润为正、股东盈余为负", "资本开支吃掉全部现金，即原文的“低市盈率陷阱”"),
    ("loss_making", "近三年平均亏损", "没有可资本化的盈余"),
    ("financial", "银行、保险、券商", "自由现金流概念不适用，应改用 ROE 与账面价值"),
    ("reit", "REIT", "折旧不是真实成本，应改用 FFO/AFFO"),
    ("foreign", "外国发行人", "按 IFRS 或非美元报表披露，本数据源未覆盖"),
    ("short_history", "上市或披露不足 5 年", "历史太短，无法判断盈利的稳定性"),
    ("data_gap", "缺折旧或资本开支数据", "公司使用了非标准科目，需人工补数"),
    ("stale", "最新年报过期", "已退市、被并购或停止披露"),
    ("fund", "基金、SPAC、信托", "非经营性实体"),
    ("no_data", "无财报数据", "未在 SEC 结构化数据中匹配到"),
]


def _bn(x):
    return "" if pd.isna(x) else f"{x / 1e9:,.1f}"


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{x * 100:.{d}f}%"


def _x(x):
    return "" if pd.isna(x) else f"{x:.2f}"


def _name(s):
    for tail in (" Common Stock", " Common Shares", " Class A", " Ordinary Shares",
                 " (The)", " (DE)", " Inc.", " Corporation", " Incorporated"):
        s = s.replace(tail, "")
    return s.strip()[:28]


def _flags(r):
    f = []
    if r.get("franchise") is True: f.append("特许")
    if r.get("sees_like") is True: f.append("喜诗式")
    if r.get("cyclical") is True: f.append("周期")
    if r.get("margin_ratio", np.nan) >= 1.15: f.append("利润率低于常态")
    if r.get("margin_ratio", np.nan) <= 0.85: f.append("利润率高于常态")
    if r.get("rnd_to_rev", np.nan) >= 0.15: f.append("高研发")
    if r.get("one_off") is True: f.append("已剔除一次性收益")
    if r.get("foreign") is True: f.append("外国公司")
    if r.get("mc_estimated") is True: f.append("市值为估算")
    return "、".join(f)


_TEXT_COLUMNS = {"代码", "公司", "行业", "标记"}


def _roe(x):
    return ">200%" if x > 2 else _pct(x, 0)


def _table(df, cols):
    head = "| " + " | ".join(h for h, _ in cols) + " |"
    sep = "|" + "|".join(" --- " if h in _TEXT_COLUMNS else " ---: " for h, _ in cols) + "|"
    body = ["| " + " | ".join(str(fn(r)) for _, fn in cols) + " |" for _, r in df.iterrows()]
    return "\n".join([head, sep] + body)


VALUE_COLS = [
    ("代码", lambda r: r["ticker"]),
    ("公司", lambda r: _name(r["name"])),
    ("市值(十亿$)", lambda r: _bn(r["mktcap"])),
    ("股东盈余收益率", lambda r: _pct(r["oe_yield"])),
    ("价格/保守价值", lambda r: _x(r["pv_low"])),
    ("价格/乐观价值", lambda r: _x(r["pv_high"])),
    ("隐含永续增速", lambda r: _pct(r["implied_g"])),
    ("ROE中位数", lambda r: _roe(r["roe_med"])),
    ("标记", _flags),
]


def render(df, rate, asof):
    n = len(df)
    val = df[df["bucket"] == "valued"]
    good = df[passes_quality(df)]
    L = []
    w = L.append

    w(f"# 股东盈余筛选：美股市值前 {n} 名\n")
    w(f"- 股价与市值：{asof} 收盘（Nasdaq 上市清单）")
    w(f"- 财报：SEC XBRL 年报数据，每家公司取最近一个完整财年及此前最多 {C.HIST_YEARS} 年")
    w(f"- 折现率：10 年期美债收益率 {rate * 100:.2f}%（{C.RISK_FREE_ASOF}），对应零增长估值倍数 {1 / rate:.1f} 倍")
    w("- 这是筛选结果，不是买卖建议；名单里的每一只都需要再做人工判断。\n")

    w("## 一、框架能覆盖多少\n")
    w("| 类别 | 数量 | 占比 | 说明 |\n| --- | ---: | ---: | --- |")
    counts = df["bucket"].value_counts()
    for key, label, note in BUCKETS:
        if counts.get(key, 0):
            w(f"| {label} | {counts[key]} | {counts[key] / n * 100:.1f}% | {note} |")
    w("")

    w("## 二、可估值公司的价格水平\n")
    w("“保守价值”取以下三者的最小值：第一步（净利润 + 折旧摊销 − 全部资本开支）÷ 折现率；"
      "第二步 净利润 ÷ 折现率；以及利润率高于自身十年常态时按常态下调后的第二步。"
      "它不含任何增长假设，也不含利润率修复。\n")
    pv = val["pv_low"]
    bands = [("≤ 0.5（五折以下）", pv <= 0.5), ("0.5 – 1.0", (pv > 0.5) & (pv <= 1)),
             ("1.0 – 2.0", (pv > 1) & (pv <= 2)), ("> 2.0", pv > 2)]
    w("| 价格 / 保守价值 | 公司数 | 占可估值公司 |\n| --- | ---: | ---: |")
    for label, mask in bands:
        w(f"| {label} | {int(mask.sum())} | {mask.mean() * 100:.1f}% |")
    w(f"\n中位数为 {pv.median():.2f}：典型公司的价格是零增长价值的 {pv.median():.1f} 倍，"
      f"即市场要求其股东盈余永续增长约 {val['implied_g'].median() * 100:.1f}% 才撑得住现价。\n")

    w("## 三、候选名单：价格低于保守价值\n")
    w("条件：价格/保守价值 ≤ 1，且通过质量门槛（至少 7 年记录、十年中至少 8 年盈利、"
      "十年自由现金流/净利润 ≥ 0.5、利息保障倍数不低于 3）。按折扣从深到浅排序。\n")
    cand = good[good["pv_low"] <= 1].sort_values("pv_low")
    w(f"共 {len(cand)} 只，列出前 {min(len(cand), 40)} 只：\n")
    w(_table(cand.head(40), VALUE_COLS))
    w("")

    w("## 四、“邮报式”：利润率暂时低于常态的好生意\n")
    w("条件：通过质量门槛，近三年利润率比自身十年中位数低 15% 以上，"
      "且修复后的价格/乐观价值 ≤ 1。利润率能否修复无法从数字判断，这是需要逐只研究的部分。\n")
    rep = good[(good["margin_ratio"] >= 1.15) & (good["pv_high"] <= 1)].sort_values("pv_high")
    w(_table(rep.head(25), VALUE_COLS + [
        ("利润率 现在/常态", lambda r: f"{_pct(r['margin_now'])} / {_pct(r['margin_norm'])}")]))
    w("")

    w("## 五、“喜诗式”：高回报、低资本需求、利润大部分分掉\n")
    w("条件：十年 ROE 中位数 ≥ 20%、年年盈利、资本开支 ≤ 净利润的 40%、"
      "分红加回购 ≥ 净利润的 70%、利润仍在增长。这类公司很少便宜，按价格/保守价值排序：\n")
    sees = df[is_clean(df) & (df["sees_like"] == True)].sort_values("pv_low")  # noqa: E712
    w(f"共 {len(sees)} 只，列出最便宜的 {min(len(sees), 25)} 只：\n")
    w(_table(sees.head(25), VALUE_COLS))
    w("")

    w("## 六、反面教材\n")
    w("### 低市盈率陷阱：账面盈利，但股东盈余为负\n")
    trap = df[df["bucket"] == "cash_burn"].sort_values("earn_yield", ascending=False)
    w(_table(trap.head(15), [
        ("代码", lambda r: r["ticker"]), ("公司", lambda r: _name(r["name"])),
        ("市值(十亿$)", lambda r: _bn(r["mktcap"])),
        ("市盈率", lambda r: f"{1 / r['earn_yield']:.1f}"),
        ("净利润(十亿$)", lambda r: _bn(r["ni"])),
        ("折旧摊销", lambda r: _bn(r["da"])), ("资本开支", lambda r: _bn(r["capex"])),
        ("股东盈余", lambda r: _bn(r["oe"]))]))
    w("")
    w("### 周期高点：利润率远高于自身常态的周期股\n")
    w("按当期利润看便宜，按十年常态利润率重算后的差别：\n")
    peak = val[(val["cyclical"] == True) & (val["margin_ratio"] <= 0.85)].copy()  # noqa: E712
    peak["pv_raw"] = peak["mktcap"] / np.minimum(peak["v1"], peak["v2"])
    peak = peak[peak["pv_low"] > 1.1 * peak["pv_raw"]].sort_values("pv_raw")
    w(_table(peak.head(15), [
        ("代码", lambda r: r["ticker"]), ("公司", lambda r: _name(r["name"])),
        ("行业", lambda r: (r["sic_desc"] or "")[:26]),
        ("利润率 现在/常态", lambda r: f"{_pct(r['margin_now'])} / {_pct(r['margin_norm'])}"),
        ("价格/价值(当期利润)", lambda r: _x(r["pv_raw"])),
        ("价格/价值(常态利润)", lambda r: _x(r["pv_low"]))]))
    w("")
    return "\n".join(L) + "\n"
