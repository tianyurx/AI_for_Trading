"""python -m owner_earnings_screen [fetch|screen|all] [--size N] [--rate R] [--asof YYYY-MM-DD]"""
import argparse

from . import config as C
from . import panel, report, screen, sec, universe


def fetch():
    universe.fetch(force=True)
    sec.fetch_all_frames()
    pan = panel.build()
    # ticker, SIC code and filer type for every company with a recent annual report
    sec.fetch_submissions(sorted(int(c) for c in pan.loc[pan["cy"] >= 2024, "cik"].unique()))


def main():
    ap = argparse.ArgumentParser(prog="owner_earnings_screen")
    ap.add_argument("step", choices=["fetch", "screen", "all"], nargs="?", default="all")
    ap.add_argument("--rate", type=float, default=C.RISK_FREE,
                    help="10-year Treasury yield used to capitalise owner earnings")
    ap.add_argument("--size", type=int, default=C.UNIVERSE_SIZE,
                    help="largest N companies by market cap; 0 for every listed company")
    ap.add_argument("--asof", default=C.RISK_FREE_ASOF, help="label for the output folder")
    a = ap.parse_args()
    if a.step in ("fetch", "all"):
        fetch()
    if a.step in ("screen", "all"):
        df = screen.run(rate=a.rate, size=a.size)
        out = C.RESULTS_DIR / a.asof
        out.mkdir(parents=True, exist_ok=True)
        tag = "" if a.size == C.UNIVERSE_SIZE else "_all" if not a.size else f"_top{a.size}"
        df.to_csv(out / f"screen{tag}.csv", index=False, float_format="%.6g")
        (out / f"report{tag}.md").write_text(report.render(df, a.rate, a.asof, whole_market=not a.size))
        print(f"wrote {out}/screen{tag}.csv and report{tag}.md")
        print(df["bucket"].value_counts().to_string())


if __name__ == "__main__":
    main()
