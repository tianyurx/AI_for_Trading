"""US-listed common stocks with price, market cap and sector, from Nasdaq's screener."""
import json
import re

import pandas as pd
import requests

from . import config as C

_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true"
PATH = C.DATA_DIR / "nasdaq_listing.json"

# The listing mixes common stock with notes, preferreds, units and warrants,
# each carrying the issuer's market cap. Keep only common equity.
_NOT_COMMON = re.compile(
    r"warrant|preferred|debenture|subordinated|\bnotes?\b|\bbonds?\b|\brights?\b|%"
    r"|\bzones\b|corporate units|equity units?|tangible equity|"
    r"depositary shares? .*interest in a share", re.I)


def fetch(force=False):
    if PATH.exists() and not force:
        return
    r = requests.get(_URL, headers={"User-Agent": C.USER_AGENT,
                                    "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    PATH.write_text(r.text)


def norm_ticker(t):
    """BRK/B, BRK.B and BRK-B are the same share class."""
    return re.sub(r"[^A-Z0-9]+", "-", t.strip().upper())


def load():
    rows = json.loads(PATH.read_text())["data"]["rows"]
    df = pd.DataFrame(rows)
    df["ticker"] = df["symbol"].map(norm_ticker)
    df["price"] = pd.to_numeric(df["lastsale"].str.replace(r"[$,]", "", regex=True),
                                errors="coerce")
    df["mktcap"] = pd.to_numeric(df["marketCap"], errors="coerce")
    # one day's turnover in dollars: a rough guide to how tradable the stock is
    df["dollar_volume"] = pd.to_numeric(df["volume"], errors="coerce") * df["price"]
    df = df[~df["name"].str.contains(_NOT_COMMON) & ~df["symbol"].str.contains(r"\^")]
    df = df[df["price"] > 0]
    cols = ["ticker", "name", "price", "mktcap", "dollar_volume", "country", "sector",
            "industry"]
    return df[cols].drop_duplicates("ticker").reset_index(drop=True)
