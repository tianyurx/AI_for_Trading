"""python -m owner_earnings_screen [fetch|screen|all] [--rate 0.0515] [--asof YYYY-MM-DD]"""
import argparse

from . import config as C
from . import panel, report, screen, sec, universe


def fetch():
    universe.fetch(force=True)
    sec.fetch_all_frames()
    pan = panel.build()
    # ticker lookups only for filers large enough to matter to a top-2000 list
    recent = pan[pan["cy"] >= 2024].assign(ni=lambda d: d["ni"].abs())
    size = recent.groupby("cik")[["assets", "ni", "rev"]].max()
    keep = size[(size["assets"] >= 5e7) | (size["ni"] >= 5e6) | (size["rev"] >= 5e7)]
    sec.fetch_submissions([int(c) for c in keep.sort_values("assets", ascending=False).index])


def main():
    ap = argparse.ArgumentParser(prog="owner_earnings_screen")
    ap.add_argument("step", choices=["fetch", "screen", "all"], nargs="?", default="all")
    ap.add_argument("--rate", type=float, default=C.RISK_FREE,
                    help="10-year Treasury yield used to capitalise owner earnings")
    ap.add_argument("--asof", default=C.RISK_FREE_ASOF, help="label for the output folder")
    a = ap.parse_args()
    if a.step in ("fetch", "all"):
        fetch()
    if a.step in ("screen", "all"):
        df = screen.run(rate=a.rate)
        out = C.RESULTS_DIR / a.asof
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "screen.csv", index=False, float_format="%.6g")
        (out / "report.md").write_text(report.render(df, a.rate, a.asof))
        print(f"wrote {out}/screen.csv and report.md")
        print(df["bucket"].value_counts().to_string())


if __name__ == "__main__":
    main()
