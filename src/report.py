"""Self-contained visual HTML report.

Charts are rendered with matplotlib and embedded as base64 PNGs, so the
single output/report.html file can be opened anywhere (or attached to the
submission email) with no external assets.
"""
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import ASSET_BY_TICKER
from .sentiment import direction_label


def _fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _bar_chart(df: pd.DataFrame, value: str, title: str, color_by=None) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = [f"{t} · {ASSET_BY_TICKER[t]['name']}" for t in df["ticker"]]
    colors = None
    if color_by is not None:
        colors = ["#2e7d32" if v > 0.05 else "#c62828" if v < -0.05 else "#757575"
                  for v in df[color_by]]
    ax.barh(labels[::-1], df[value].values[::-1], color=colors)
    ax.set_title(title, fontsize=11)
    for i, v in enumerate(df[value].values[::-1]):
        ax.text(v, i, f" {v:,.2f}" if isinstance(v, float) else f" {v:,}",
                va="center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_b64(fig)


def _ticker_card(t) -> str:
    sent_cls = ("pos" if t["sentiment_score"] > 0.05 else
                "neg" if t["sentiment_score"] < -0.05 else "neu")
    return f"""
    <div class="card">
      <h3>{t['ticker']} — {t['asset_name']} <span class="cur">{t['currency']}</span></h3>
      <div class="price">Close: <b>{t['current_price']:,.2f}</b></div>
      <div>Sentiment: <span class="{sent_cls}"><b>{t['sentiment_score']:+.2f}</b>
        ({t['direction']})</span> · Mentions: <b>{t['mentions']:,}</b>
        · News items: {t['news_count']}</div>
      <div>Model n+1: <b>{t['pred_direction']}</b> (P(up) = {t['prob_up']:.0%})
        → predicted next close <b>{t['pred_next_close']:,.2f}</b></div>
      <div>Position (rule-based): <b>{t['stance']}</b></div>
      <div class="levels">Support: {t['support']:,.2f} (pivot) / {t['support_swing']:,.2f} (20d low)
        · Resistance: {t['resistance']:,.2f} (pivot) / {t['resistance_swing']:,.2f} (20d high)</div>
    </div>"""


def build_report(summary: pd.DataFrame, metrics: dict, provenance: dict,
                 generated_at: str) -> str:
    sections = []
    for exchange in ["HK", "KR"]:
        d = summary[summary["exchange"] == exchange].copy()
        if d.empty:
            continue
        d = d.sort_values("mentions", ascending=False)
        title = "Hong Kong (Hang Seng)" if exchange == "HK" else "South Korea (KRX)"
        mentions_chart = _bar_chart(d, "mentions",
                                    f"{title} — social mentions (last 10 days)")
        sent_chart = _bar_chart(d, "sentiment_score",
                                f"{title} — engagement-weighted sentiment",
                                color_by="sentiment_score")
        cards = "\n".join(_ticker_card(r) for _, r in d.iterrows())
        sections.append(f"<h2>{title}</h2>"
                        f"<img src='data:image/png;base64,{mentions_chart}'/>"
                        f"<img src='data:image/png;base64,{sent_chart}'/>"
                        f"<div class='cards'>{cards}</div>")

    bt_rows = "".join(
        f"<tr><td>{k}</td><td>{v['n_test']}</td>"
        f"<td>{v['direction_accuracy']:.0%}</td>"
        f"<td>{v['baseline_accuracy']:.0%}</td>"
        f"<td>{v['price_mae']:,.2f}</td><td>{v['naive_price_mae']:,.2f}</td></tr>"
        for k, v in metrics.items())
    prov = "".join(f"<li>{k}: <b>{v}</b></li>" for k, v in provenance.items())

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Sentiment Price-Prediction Report — HK &amp; KR</title>
<style>
 body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 2rem auto;
        max-width: 900px; color: #212121; line-height: 1.45; padding: 0 1rem; }}
 h1 {{ font-size: 1.5rem; }} h2 {{ margin-top: 2.2rem; border-bottom: 2px solid #eee; }}
 img {{ max-width: 100%; margin: .5rem 0; }}
 .cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; }}
 .card {{ border: 1px solid #ddd; border-radius: 8px; padding: .8rem 1rem; }}
 .card h3 {{ margin: .1rem 0 .4rem; font-size: 1rem; }}
 .cur, .levels {{ color: #666; font-size: .85rem; }}
 .pos {{ color: #2e7d32; }} .neg {{ color: #c62828; }} .neu {{ color: #757575; }}
 table {{ border-collapse: collapse; width: 100%; }}
 td, th {{ border: 1px solid #ddd; padding: .35rem .5rem; text-align: right; }}
 td:first-child, th:first-child {{ text-align: left; }}
 .note {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px;
         padding: .6rem 1rem; }}
</style></head><body>
<h1>Social Sentiment → Next-Day Price Prediction</h1>
<p>Hang Seng (Hong Kong) &amp; KRX (South Korea) · Generated {generated_at}</p>
<div class="note"><b>Data provenance</b><ul>{prov}</ul>
<p>Sentiment history covers only the last 10 days, so the backtest below is
small-sample: treat it as a pipeline validation, not proof of a tradable
edge. This report is an internship assignment artefact, not investment
advice.</p></div>
{''.join(sections)}
<h2>Backtest — walk-forward, out-of-sample (“check your results”)</h2>
<table><tr><th>Scope</th><th>Test rows</th><th>Direction accuracy</th>
<th>Majority-class baseline</th><th>Price MAE (model)</th>
<th>Price MAE (naive = today)</th></tr>{bt_rows}</table>
<h2>Method in one paragraph</h2>
<p>Posts are collected per exchange from two listed sources, scored with a
transparent local lexicon/VADER method (English, Chinese and Korean market
terms — see README), aggregated per ticker per trading day with
engagement weighting, merged with Exa news sentiment (or the labelled RSS
fallback) and price features, and fed to a pooled logistic-regression /
ridge model per exchange. Support/resistance are classic pivot levels from
the previous session plus 20-day swing extremes. Full details, code and
limitations: see the project README.</p>
</body></html>"""


def ticker_summary(features: pd.DataFrame, posts: pd.DataFrame,
                   news: pd.DataFrame, predictions: pd.DataFrame,
                   levels: dict) -> pd.DataFrame:
    """One row per ticker for the report cards/rankings."""
    rows = []
    pred = predictions.set_index("ticker") if not predictions.empty else None
    for ticker, a in ASSET_BY_TICKER.items():
        tp = posts[posts["ticker"] == ticker] if not posts.empty else posts
        tn = news[news["ticker"] == ticker] if not news.empty else news
        if len(tp):
            weights = 1.0 + np.log1p(tp["views"].clip(lower=0)) + tp["likes"].clip(lower=0)
            sent = float(np.average(tp["sentiment"], weights=weights))
        else:
            sent = 0.0
        lv = levels.get(ticker, {})
        pr = pred.loc[ticker] if pred is not None and ticker in pred.index else None
        rows.append(dict(
            exchange=a["exchange"], ticker=ticker, asset_name=a["name"],
            currency=a["currency"], mentions=int(len(tp)),
            news_count=int(len(tn)), sentiment_score=sent,
            direction=direction_label(sent),
            current_price=lv.get("close", float("nan")),
            support=lv.get("support_pivot", float("nan")),
            support_swing=lv.get("support_swing", float("nan")),
            resistance=lv.get("resistance_pivot", float("nan")),
            resistance_swing=lv.get("resistance_swing", float("nan")),
            pred_direction=pr["pred_dir"] if pr is not None else "n/a",
            prob_up=float(pr["prob_up"]) if pr is not None else 0.0,
            pred_next_close=float(pr["pred_next_close"]) if pr is not None else float("nan"),
            stance=pr["stance"] if pr is not None else "n/a"))
    return pd.DataFrame(rows)
