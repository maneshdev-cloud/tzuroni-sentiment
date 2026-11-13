#!/usr/bin/env python3
"""End-to-end pipeline for the CrowdWisdomTrading / TZURONI assignment.

    python run_pipeline.py [--mode auto|apify|direct]

Stages: prices -> social posts -> news -> sentiment -> features ->
walk-forward backtest + live n+1 predictions -> visual HTML report.

Mode "auto" (default) uses Apify/Exa when the tokens exist in .env and
falls back to the direct public-endpoint providers otherwise; every row is
stamped with its fetch mode / provider so provenance is explicit.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
from src import (config, features as feat_mod, model as model_mod, news,
                 prices as prices_mod, report as report_mod, sentiment,
                 social_apify, social_direct)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auto", "apify", "direct"],
                    default="auto")
    args = ap.parse_args()

    use_apify = config.APIFY_TOKEN if args.mode == "auto" else args.mode == "apify"
    use_exa = bool(config.EXA_API_KEY) if args.mode == "auto" else args.mode == "apify"

    # 1) Prices -------------------------------------------------------------
    prices = prices_mod.download_prices()
    prices.to_csv(config.PROCESSED_DIR / "prices.csv", index=False)
    print(f"[prices] {len(prices)} daily bars, "
          f"{prices['date'].min().date()} .. {prices['date'].max().date()}")

    # 2) Social posts ---------------------------------------------------------
    social_mode = "direct"
    if use_apify:
        try:
            posts = social_apify.fetch_all_apify()
            social_mode = "apify"
        except Exception as e:  # token invalid / actor failed -> fall back
            print(f"[social] Apify failed ({e}); falling back to direct")
            posts = social_direct.fetch_all_direct()
    else:
        posts = social_direct.fetch_all_direct()
    if not posts.empty:
        posts = posts.sort_values("published_at").reset_index(drop=True)
        posts = posts.drop_duplicates(subset=["source", "url", "ticker"])
        posts["sentiment"] = posts["text"].map(
            lambda t: sentiment.score_text(sentiment.strip_urls(t)))
    posts.to_csv(config.RAW_DIR / "posts_raw.csv", index=False)
    print(f"[social:{social_mode}] {len(posts)} posts")
    if not posts.empty:
        print(posts.groupby(["exchange", "source"]).size()
              .rename("posts").to_string())

    # 3) News -----------------------------------------------------------------
    news_df = news.fetch_all_news(use_exa=use_exa)
    if not news_df.empty:
        news_df["sentiment"] = (news_df["title"].fillna("") + " "
                                + news_df["snippet"].fillna("")).map(
                                    sentiment.score_text)
    else:
        news_df["sentiment"] = pd.Series(dtype=float)
    news_df.to_csv(config.RAW_DIR / "news_raw.csv", index=False)
    news_provider = ("exa" if use_exa else "googlenews_rss_fallback")
    print(f"[news:{news_provider}] {len(news_df)} items")

    # 4) Features ---------------------------------------------------------------
    cutoff_date = (datetime.now(timezone.utc)
                   - timedelta(days=config.LOOKBACK_DAYS)).date()
    window_start = prices.loc[prices["date"] >= pd.Timestamp(cutoff_date),
                              "date"].min()
    feats = feat_mod.build_features(prices, posts, news_df, window_start)
    feats.to_csv(config.PROCESSED_DIR / "features.csv", index=False)
    print(f"[features] {len(feats)} ticker-days from {window_start.date()}")

    # 5) Backtest (walk-forward) + live n+1 predictions -------------------------
    backtest, metrics = model_mod.walk_forward(feats)
    backtest.to_csv(config.OUTPUT_DIR / "backtest.csv", index=False)
    predictions = model_mod.live_predictions(feats)
    predictions.to_csv(config.OUTPUT_DIR / "predictions.csv", index=False)
    with open(config.OUTPUT_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    for scope, m in metrics.items():
        print(f"[backtest:{scope}] n={m['n_test']} "
              f"dir-acc={m['direction_accuracy']:.2f} "
              f"(baseline {m['baseline_accuracy']:.2f}) "
              f"price-MAE={m['price_mae']:.2f} vs naive {m['naive_price_mae']:.2f}")
    print(f"[predictions] {len(predictions)} live n+1 forecasts")

    # 6) Visual report ---------------------------------------------------------
    levels = {a["ticker"]: prices_mod.support_resistance(prices, a["ticker"])
              for a in config.ASSETS}
    summary = report_mod.ticker_summary(feats, posts, news_df, predictions,
                                        levels)
    summary.to_csv(config.OUTPUT_DIR / "ticker_summary.csv", index=False)
    by_source = (posts.groupby("source").size().to_dict()
                 if not posts.empty else {})
    provenance = {
        "Social fetch mode": social_mode,
        "Social sources (posts)": ", ".join(
            f"{k}: {v}" for k, v in by_source.items()) or "none",
        "News provider": news_provider,
        "News items": len(news_df),
        "Price providers used": ", ".join(
            sorted(prices["price_source"].unique())),
    }
    html = report_mod.build_report(
        summary, metrics, provenance,
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    out = config.OUTPUT_DIR / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"[report] {out} ({len(html)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
