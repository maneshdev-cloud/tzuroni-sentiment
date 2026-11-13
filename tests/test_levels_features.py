import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.features import build_features
from src.prices import support_resistance


def _synthetic_prices(n=30):
    dates = pd.bdate_range("2026-10-01", periods=n)
    close = 100 + np.cumsum(np.random.default_rng(7).normal(0, 1, n))
    return pd.DataFrame({
        "date": dates, "open": close, "high": close + 1.5, "low": close - 1.5,
        "close": close, "volume": 1000, "ticker": "0700.HK", "exchange": "HK"})


def test_support_below_resistance():
    prices = _synthetic_prices()
    lv = support_resistance(prices, "0700.HK")
    assert lv["support_pivot"] < lv["resistance_pivot"]
    assert lv["support_swing"] <= lv["support_pivot"] + 5  # sanity band
    assert lv["resistance_swing"] >= lv["close"] - 5


def test_features_have_no_lookahead_target_on_last_day():
    prices = _synthetic_prices()
    empty_posts = pd.DataFrame(columns=["ticker", "published_at", "sentiment",
                                        "views", "likes"])
    empty_news = pd.DataFrame(columns=["ticker", "published_at", "sentiment"])
    feats = build_features(prices, empty_posts, empty_news, prices["date"].min())
    last = feats.sort_values("date").iloc[-1]
    assert pd.isna(last["next_close"])  # latest day is the live-prediction row
    earlier = feats.sort_values("date").iloc[0]
    assert not pd.isna(earlier["next_close"])
    assert set(feats["mentions"]) == {0}  # no posts -> zero-filled, not fake
