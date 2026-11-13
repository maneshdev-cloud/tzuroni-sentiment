"""News sentiment per asset.

Primary (the brief's requirement): Exa (exa.com) neural search over recent
news, key from EXA_API_KEY in .env.

Fallback (only when no Exa key exists): Google News RSS — real headlines
from real publishers, stamped provider="googlenews_rss_fallback" so the
report never confuses the two.
"""
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

from .config import ASSETS, EXA_API_KEY, LOOKBACK_DAYS, USER_AGENT

NEWS_COLUMNS = ["ticker", "exchange", "published_at", "title", "snippet",
                "source_name", "url", "provider"]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_COLUMNS)


def _query_for(asset: dict) -> str:
    if asset["exchange"] == "KR":
        return f"{asset['name']} {asset['local_name']} stock"
    return f"{asset['name']} stock Hong Kong"


def fetch_exa(asset: dict, cutoff: datetime) -> pd.DataFrame:
    if not EXA_API_KEY:
        raise RuntimeError("EXA_API_KEY is not set in .env")
    payload = {
        "query": _query_for(asset),
        "type": "auto",
        "category": "news",
        "numResults": 10,
        "startPublishedDate": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contents": {"text": {"maxCharacters": 500}},
    }
    r = requests.post("https://api.exa.ai/search", json=payload, timeout=40,
                      headers={"x-api-key": EXA_API_KEY,
                               "User-Agent": USER_AGENT})
    r.raise_for_status()
    rows = []
    for res in r.json().get("results", []):
        ts = res.get("publishedDate")
        ts = (datetime.fromisoformat(ts.replace("Z", "+00:00"))
              if ts else datetime.now(timezone.utc))
        rows.append(dict(
            ticker=asset["ticker"], exchange=asset["exchange"],
            published_at=ts, title=res.get("title", ""),
            snippet=(res.get("text") or "")[:500],
            source_name=res.get("author") or "Exa result",
            url=res.get("url", ""), provider="exa"))
    return pd.DataFrame(rows, columns=NEWS_COLUMNS)


def fetch_google_news_rss(asset: dict, cutoff: datetime) -> pd.DataFrame:
    q = urllib.parse.quote(_query_for(asset) +
                           f" when:{LOOKBACK_DAYS}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    rows = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        try:
            ts = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        src = item.find("source")
        rows.append(dict(
            ticker=asset["ticker"], exchange=asset["exchange"],
            published_at=ts, title=title, snippet="",
            source_name=src.text if src is not None else "Google News",
            url=item.findtext("link") or "",
            provider="googlenews_rss_fallback"))
    return pd.DataFrame(rows, columns=NEWS_COLUMNS)


def fetch_all_news(use_exa: bool) -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    frames = []
    for a in ASSETS:
        try:
            frames.append(fetch_exa(a, cutoff) if use_exa
                          else fetch_google_news_rss(a, cutoff))
        except (requests.RequestException, RuntimeError, ET.ParseError):
            continue
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty()
