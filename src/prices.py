"""Price data: yfinance primary, Naver Stock API fallback.

yfinance (Yahoo Finance) needs no key and is the documented default.  In
some sandboxes Yahoo is unreachable; the fallback is Naver's public stock
API, which serves the same daily OHLCV fields for both KRX
(m.stock.naver.com/api/stock/{code}/price) and HKEX
(api.stock.naver.com/stock/{code}.HK/price) tickers.  The provider used is
recorded per row in the `price_source` column — never silently mixed.

Support/resistance method (documented, deliberately simple):
* Classic floor-trader pivot points from the *previous* session
  (P, R1, S1) — widely used, fully deterministic.
* 20-session swing high / swing low as the outer resistance / support.
"""
import pandas as pd
import requests
import yfinance as yf

from .config import ASSETS, PRICE_HISTORY_DAYS, USER_AGENT


def _from_yahoo(asset: dict, days: int) -> pd.DataFrame:
    hist = yf.Ticker(asset["ticker"]).history(period=f"{days}d", timeout=12,
                                              auto_adjust=False)
    if hist.empty:
        return pd.DataFrame()
    hist = hist.reset_index()
    hist["date"] = (pd.to_datetime(hist["Date"]).dt.tz_localize(None)
                    .dt.normalize())
    out = hist[["date", "Open", "High", "Low", "Close", "Volume"]].copy()
    out.columns = ["date", "open", "high", "low", "close", "volume"]
    return out


def _num(v) -> float:
    return float(str(v).replace(",", ""))


def _from_naver(asset: dict, days: int) -> pd.DataFrame:
    # Both Naver price endpoints cap pageSize at 60 (100 -> HTTP 400).
    if asset["exchange"] == "KR":
        url = (f"https://m.stock.naver.com/api/stock/{asset['code']}"
               f"/price?pageSize=60&page={{page}}")
    else:
        url = (f"https://api.stock.naver.com/stock/{asset['code']}.HK"
               f"/price?pageSize=60&page={{page}}")
    rows = []
    page = 1
    while len(rows) < days and page <= 5:
        r = requests.get(url.format(page=page), timeout=30,
                         headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        page += 1
    recs = []
    for b in rows[:days]:
        try:
            recs.append(dict(
                date=pd.to_datetime(b["localTradedAt"]).normalize(),
                open=_num(b["openPrice"]), high=_num(b["highPrice"]),
                low=_num(b["lowPrice"]), close=_num(b["closePrice"]),
                volume=_num(b.get("accumulatedTradingVolume") or 0)))
        except (KeyError, ValueError):
            continue
    return pd.DataFrame(recs)


def download_prices(days: int = PRICE_HISTORY_DAYS) -> pd.DataFrame:
    """Daily OHLCV for every configured asset, long format."""
    frames = []
    yahoo_dead = False  # probe once; if Yahoo is unreachable, don't stall x10
    for a in ASSETS:
        out, source = pd.DataFrame(), "yahoo"
        if not yahoo_dead:
            try:
                out = _from_yahoo(a, days)
            except Exception:
                out = pd.DataFrame()
            if out.empty:
                yahoo_dead = True
        if out.empty:
            out, source = _from_naver(a, days), "naver_api_fallback"
        if out.empty:
            continue
        # Normalise to tz-naive dates: Naver's HK feed returns offset-aware
        # timestamps while KR/Yahoo are naive — mixing them breaks sorting.
        out["date"] = (pd.to_datetime(out["date"], utc=True)
                       .dt.tz_localize(None).dt.normalize())
        out["ticker"] = a["ticker"]
        out["exchange"] = a["exchange"]
        out["price_source"] = source
        frames.append(out)
    if not frames:
        raise RuntimeError("no price data from yfinance or the Naver fallback")
    df = pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"])
    return df.drop_duplicates(subset=["ticker", "date"])


def support_resistance(prices: pd.DataFrame, ticker: str) -> dict:
    """Pivot + swing support/resistance from the latest completed bar."""
    d = prices[prices["ticker"] == ticker].sort_values("date")
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else last
    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3
    r1 = 2 * pivot - prev["low"]
    s1 = 2 * pivot - prev["high"]
    window = d.tail(20)
    return {
        "ticker": ticker,
        "date": last["date"],
        "close": float(last["close"]),
        "pivot": float(pivot),
        "support_pivot": float(s1),
        "resistance_pivot": float(r1),
        "support_swing": float(window["low"].min()),
        "resistance_swing": float(window["high"].max()),
    }
