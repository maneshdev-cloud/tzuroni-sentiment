"""Next-day (n+1) prediction with walk-forward out-of-sample validation.

Design (documented in the README):
* One pooled model per exchange (5 tickers share a model — with ~10 days of
  sentiment history a per-ticker model would be pure noise).
* Direction: Logistic Regression on standardised features.
* Price: Ridge regression predicting next-day *return*; predicted price =
  today's close x (1 + predicted return).
* Validation: walk-forward — for every test day, the model is trained only
  on earlier days.  No shuffling, no look-ahead.
* Baselines reported alongside: majority-class direction accuracy and the
  naive "tomorrow = today" price forecast, so the numbers can be judged
  honestly.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLS

MIN_TRAIN_DAYS = 4


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame):
    """Fit on `train`, predict rows of `test`. Returns (dir, prob_up, ret)."""
    Xtr, Xte = train[FEATURE_COLS].values, test[FEATURE_COLS].values
    scaler = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
    y_dir = train["next_dir"].values
    if len(np.unique(y_dir)) < 2:
        # Degenerate training window: predict the only class seen.
        p = float(y_dir[0])
        dirs = np.full(len(test), p)
        probs = np.full(len(test), p)
    else:
        clf = LogisticRegression(max_iter=1000, C=1.0)
        clf.fit(Xtr_s, y_dir)
        dirs = clf.predict(Xte_s)
        probs = clf.predict_proba(Xte_s)[:, list(clf.classes_).index(1.0)]
    reg = Ridge(alpha=1.0)
    reg.fit(Xtr_s, train["next_ret"].values)
    rets = reg.predict(Xte_s)
    return dirs, probs, rets


def walk_forward(features: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Backtest every exchange; returns (per-row results, metrics dict)."""
    results, metrics = [], {}
    labelled = features.dropna(subset=["next_dir"]).copy()
    for exchange, group in labelled.groupby("exchange"):
        days = sorted(group["date"].unique())
        rows = []
        for i, day in enumerate(days):
            if i < MIN_TRAIN_DAYS:
                continue
            train = group[group["date"] < day]
            test = group[group["date"] == day]
            if train.empty or test.empty:
                continue
            dirs, probs, rets = _fit_predict(train, test)
            for j, (_, r) in enumerate(test.iterrows()):
                rows.append(dict(
                    exchange=exchange, ticker=r["ticker"], date=r["date"],
                    next_date=r["next_date"], close=float(r["close"]),
                    actual_next_close=float(r["next_close"]),
                    pred_next_close=float(r["close"] * (1 + rets[j])),
                    actual_dir=int(r["next_dir"]), pred_dir=int(dirs[j]),
                    prob_up=float(probs[j])))
        if not rows:
            continue
        rdf = pd.DataFrame(rows)
        results.append(rdf)
        acc = float((rdf["pred_dir"] == rdf["actual_dir"]).mean())
        base = float(max(rdf["actual_dir"].mean(), 1 - rdf["actual_dir"].mean()))
        metrics[exchange] = dict(
            n_test=int(len(rdf)), direction_accuracy=acc,
            baseline_accuracy=base,
            price_mae=float(np.abs(rdf["pred_next_close"] - rdf["actual_next_close"]).mean()),
            naive_price_mae=float(np.abs(rdf["close"] - rdf["actual_next_close"]).mean()))
    out = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    if metrics:
        allr = out
        metrics["ALL"] = dict(
            n_test=int(len(allr)),
            direction_accuracy=float((allr["pred_dir"] == allr["actual_dir"]).mean()),
            baseline_accuracy=float(max(allr["actual_dir"].mean(),
                                        1 - allr["actual_dir"].mean())),
            price_mae=float(np.abs(allr["pred_next_close"] - allr["actual_next_close"]).mean()),
            naive_price_mae=float(np.abs(allr["close"] - allr["actual_next_close"]).mean()))
    return out, metrics


def _stance(prob_up: float, sentiment: float) -> str:
    """Rule-based 'position if any' from model probability + sentiment."""
    if prob_up >= 0.60 and sentiment >= 0.05:
        return "Long bias"
    if prob_up <= 0.40 and sentiment <= -0.05:
        return "Avoid / short bias"
    return "Neutral — no position"


def live_predictions(features: pd.DataFrame) -> pd.DataFrame:
    """Train on all labelled rows; predict the latest (unlabelled) day."""
    labelled = features.dropna(subset=["next_dir"])
    latest = features[features["next_close"].isna()]
    rows = []
    for exchange, group in latest.groupby("exchange"):
        train = labelled[labelled["exchange"] == exchange]
        if train.empty:
            continue
        dirs, probs, rets = _fit_predict(train, group)
        for j, (_, r) in enumerate(group.iterrows()):
            rows.append(dict(
                exchange=exchange, ticker=r["ticker"], date=r["date"],
                close=float(r["close"]),
                pred_next_close=float(r["close"] * (1 + rets[j])),
                pred_dir="Up" if dirs[j] == 1 else "Down",
                prob_up=float(probs[j]),
                stance=_stance(float(probs[j]), float(r["sent_ew"]))))
    return pd.DataFrame(rows)
