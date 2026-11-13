"""Feature engineering: align social/news sentiment to trading days.

Alignment rule (documented, no look-ahead): a post belongs to trading day
*t* if its UTC calendar date falls in (previous trading day, t].  Weekend
posts therefore roll into Monday, and every feature used to predict day
t+1 is built only from information available at the close of day t.
"""
import numpy as np
import pandas as pd


def _daily_sentiment(posts: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Per (ticker, trading day) social aggregates."""
    rows = []
    if posts.empty:
        return pd.DataFrame(columns=["ticker", "date", "mentions", "sent_mean",
                                     "sent_ew", "pos_share", "total_views",
                                     "total_likes"])
    posts = posts.copy()
    posts["post_date"] = posts["published_at"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    for ticker, p in prices.groupby("ticker"):
        days = sorted(p["date"].unique())
        tp = posts[posts["ticker"] == ticker]
        for i, d in enumerate(days):
            start = days[i - 1] if i > 0 else d - pd.Timedelta(days=4)
            w = tp[(tp["post_date"] > start) & (tp["post_date"] <= d)]
            if w.empty:
                rows.append(dict(ticker=ticker, date=d, mentions=0,
                                 sent_mean=0.0, sent_ew=0.0, pos_share=0.0,
                                 total_views=0, total_likes=0))
                continue
            weights = 1.0 + np.log1p(w["views"].clip(lower=0)) + w["likes"].clip(lower=0)
            rows.append(dict(
                ticker=ticker, date=d, mentions=len(w),
                sent_mean=float(w["sentiment"].mean()),
                sent_ew=float(np.average(w["sentiment"], weights=weights)),
                pos_share=float((w["sentiment"] > 0.05).mean()),
                total_views=int(w["views"].sum()),
                total_likes=int(w["likes"].sum())))
    return pd.DataFrame(rows)


def _daily_news(news: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if news.empty:
        return pd.DataFrame(columns=["ticker", "date", "news_count", "news_sent"])
    news = news.copy()
    news["post_date"] = news["published_at"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    for ticker, p in prices.groupby("ticker"):
        days = sorted(p["date"].unique())
        tn = news[news["ticker"] == ticker]
        for i, d in enumerate(days):
            start = days[i - 1] if i > 0 else d - pd.Timedelta(days=4)
            w = tn[(tn["post_date"] > start) & (tn["post_date"] <= d)]
            rows.append(dict(ticker=ticker, date=d, news_count=len(w),
                             news_sent=float(w["sentiment"].mean()) if len(w) else 0.0))
    return pd.DataFrame(rows)


def build_features(prices: pd.DataFrame, posts: pd.DataFrame,
                   news: pd.DataFrame, window_start) -> pd.DataFrame:
    """One row per (ticker, trading day) inside the scrape window."""
    prices = prices.copy().sort_values(["ticker", "date"])
    prices["ret_1d"] = prices.groupby("ticker")["close"].pct_change()
    prices["ret_5d"] = prices.groupby("ticker")["close"].pct_change(5)
    prices["vol_5d"] = (prices.groupby("ticker")["ret_1d"]
                        .rolling(5).std().reset_index(level=0, drop=True))
    prices["next_close"] = prices.groupby("ticker")["close"].shift(-1)
    prices["next_date"] = prices.groupby("ticker")["date"].shift(-1)

    feat = prices.merge(_daily_sentiment(posts, prices),
                        on=["ticker", "date"], how="left")
    feat = feat.merge(_daily_news(news, prices), on=["ticker", "date"], how="left")
    feat = feat.fillna({"mentions": 0, "sent_mean": 0.0, "sent_ew": 0.0,
                        "pos_share": 0.0, "total_views": 0, "total_likes": 0,
                        "news_count": 0, "news_sent": 0.0, "ret_1d": 0.0,
                        "ret_5d": 0.0, "vol_5d": 0.0})
    feat = feat[feat["date"] >= window_start].copy()
    feat["next_ret"] = feat["next_close"] / feat["close"] - 1
    feat["next_dir"] = (feat["next_ret"] > 0).astype(float)
    feat.loc[feat["next_close"].isna(), "next_dir"] = np.nan
    return feat.sort_values(["exchange", "ticker", "date"]).reset_index(drop=True)


FEATURE_COLS = ["mentions", "sent_mean", "sent_ew", "pos_share",
                "total_views", "total_likes", "news_count", "news_sent",
                "ret_1d", "ret_5d", "vol_5d"]
