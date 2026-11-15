"""Rate-limited, cached access to the SEC's XBRL "frames" and submissions APIs.

A frame is one concept for one period across every filer, so a decade of
fundamentals for the whole market is a few hundred requests rather than one
bulky request per company.
"""
import gzip
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import config as C

_FRAMES = "https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# Seconds between requests, shared by all threads: ~7/s, under the SEC's 10/s
# fair-access limit. A one-item list so callers can slow it down in place.
MIN_INTERVAL = [0.14]

_lock = threading.Lock()
_last = [0.0]
_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": C.USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        _local.s = s
    return _local.s


def _get(url):
    """GET with global pacing and backoff. Returns parsed JSON, or None on 404."""
    for attempt in range(6):
        with _lock:
            wait = _last[0] + MIN_INTERVAL[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        try:
            r = _session().get(url, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        time.sleep(2 ** attempt)        # 403/429/5xx: back off and retry
    raise RuntimeError(f"giving up on {url} (last status {r.status_code})")


def frame_path(tag, period):
    return C.DATA_DIR / "frames" / tag / f"{period}.json.gz"


def fetch_frame(tag, unit, period):
    """Download one frame into the cache as compact [cik, start, end, val] rows."""
    path = frame_path(tag, period)
    if path.exists():
        return
    js = _get(_FRAMES.format(tax="us-gaap", tag=tag, unit=unit, period=period))
    rows = [] if js is None else [[d["cik"], d.get("start"), d["end"], d["val"]]
                                  for d in js["data"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(rows, f)
    tmp.rename(path)


def load_frame(tag, period):
    path = frame_path(tag, period)
    if not path.exists():
        return []
    with gzip.open(path, "rt") as f:
        return json.load(f)


def frame_jobs():
    years = range(C.FIRST_YEAR, C.LAST_YEAR + 1)
    jobs = []
    for tags in C.DURATION_TAGS.values():
        jobs += [(t, "USD", f"CY{y}") for t in tags for y in years]
    for tags in C.SHARE_TAGS.values():
        jobs += [(t, "shares", f"CY{y}") for t in tags for y in years]
    for tags in C.INSTANT_TAGS.values():
        jobs += [(t, "USD", f"CY{y}Q{q}I") for t in tags for y in years for q in (1, 2, 3, 4)]
    return jobs


def fetch_all_frames(workers=6, log=print):
    jobs = [j for j in frame_jobs() if not frame_path(j[0], j[2]).exists()]
    log(f"frames: {len(jobs)} to download")
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(lambda j: fetch_frame(*j), jobs), 1):
            if i % 100 == 0:
                log(f"  frames {i}/{len(jobs)}")


# ---- submissions: ticker <-> CIK, SIC code, filer type ---------------------
SUBMISSIONS_PATH = C.DATA_DIR / "submissions.jsonl"


def load_submissions():
    out = {}
    if SUBMISSIONS_PATH.exists():
        with open(SUBMISSIONS_PATH) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:      # blank or partial line from an interrupted run
                    continue
                out[d["cik"]] = d
    return out


def _submission(cik):
    js = _get(_SUBMISSIONS.format(cik=cik))
    if js is None:
        return {"cik": cik, "missing": True}
    forms = js.get("filings", {}).get("recent", {}).get("form", [])
    annual = [f for f in forms if f in ("10-K", "20-F", "40-F")]
    return {
        "cik": cik,
        "name": js.get("name"),
        "tickers": js.get("tickers") or [],
        "exchanges": js.get("exchanges") or [],
        "sic": int(js["sic"]) if js.get("sic") else None,
        "sic_desc": js.get("sicDescription"),
        "entity_type": js.get("entityType"),
        "fye": js.get("fiscalYearEnd"),
        "annual_form": annual[0] if annual else None,
    }


def fetch_submissions(ciks, workers=16, log=print):
    have = load_submissions()
    todo = [c for c in ciks if c not in have]
    log(f"submissions: {len(todo)} to download ({len(have)} cached)")
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as ex, open(SUBMISSIONS_PATH, "a") as f:
        f.write("\n")                  # terminate any partial line
        for i, d in enumerate(ex.map(_submission, todo), 1):
            f.write(json.dumps(d) + "\n")
            if i % 500 == 0:
                f.flush()
                log(f"  submissions {i}/{len(todo)}")
