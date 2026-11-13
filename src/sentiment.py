"""Transparent, local sentiment scoring.

Method (also documented in the README):
* English / Latin-script text  -> VADER compound score, nudged by a small
  finance-specific lexicon (words like "beat", "downgrade", "selloff" that
  general lexicons score weakly).
* Chinese / Korean text        -> keyword lexicon counting: hand-built lists
  of bullish / bearish market terms in Traditional/Simplified Chinese and
  Korean. Score = (pos - neg) / (pos + neg + 1), in [-1, 1].
* Mixed text                   -> average of whichever scorers fire.

No model is downloaded and no text leaves the machine. The lexicons are
deliberately small and readable — a reviewer can audit every word.
"""
import re

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER = SentimentIntensityAnalyzer()
except Exception:  # pragma: no cover - vader is in requirements.txt
    _VADER = None

# --- finance-specific English terms (weight 1 each unless noted) -----------
EN_POS = {
    "bullish", "beat", "beats", "upgrade", "upgraded", "outperform", "rally",
    "rallies", "surge", "surged", "soar", "soared", "breakout", "buyback",
    "dividend", "record high", "all-time high", "strong demand", "long",
    "accumulate", "momentum", "upside", "rebound", "recovery", "growth",
}
EN_NEG = {
    "bearish", "miss", "missed", "downgrade", "downgraded", "underperform",
    "plunge", "plunged", "selloff", "sell-off", "crash", "crashed", "slump",
    "weak demand", "short", "bubble", "overvalued", "lawsuit", "probe",
    "warning", "cut guidance", "layoffs", "downside", "tumble", "tumbled",
}

# --- Chinese (Traditional + Simplified) market terms -----------------------
ZH_POS = ["上漲", "上涨", "升勢", "升势", "大升", "急升", "突破", "利好", "買入",
          "买入", "買盤", "买盘", "看好", "強勢", "强势", "新高", "反彈", "反弹",
          "賺", "赚", "牛市", "升穿", "做好", "入貨", "入货", "加倉", "加仓",
          "跑贏", "跑赢", "盈喜", "增長", "增长"]
ZH_NEG = ["下跌", "大跌", "急跌", "挫", "利空", "利淡", "賣出", "卖出", "沽出",
          "看淡", "弱勢", "弱势", "新低", "虧", "亏", "熊市", "跌穿", "暴跌",
          "插水", "沽空", "做空", "減持", "减持", "盈警", "停牌", "爆倉", "爆仓",
          "回落", "走弱", "倒跌"]

# --- Korean market terms ----------------------------------------------------
KO_POS = ["상승", "급등", "강세", "매수", "호재", "신고가", "반등", "상향",
          "흑자", "성장", "수혜", "돌파", "인상", "기대감", "순매수"]
KO_NEG = ["하락", "급락", "약세", "매도", "악재", "신저가", "우려", "하향",
          "적자", "손실", "매물", "폭락", "순매도", "리스크", "조정"]

_CJK = re.compile(r"[\u3400-\u9fff\uac00-\ud7a3]")
_URL = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+")


def strip_urls(text: str) -> str:
    """Remove URLs before matching/scoring: a link to n.news.naver.com is
    not a mention of NAVER-the-company, and URLs carry no sentiment."""
    return _URL.sub(" ", str(text))


def _lexicon_score(text: str, pos_words, neg_words) -> float | None:
    """(pos-neg)/(pos+neg+1); None when no lexicon word appears."""
    pos = sum(text.count(w) for w in pos_words)
    neg = sum(text.count(w) for w in neg_words)
    if pos == 0 and neg == 0:
        return None
    return (pos - neg) / (pos + neg + 1)


def score_text(text: str) -> float:
    """Return a sentiment score in [-1, 1] for one post/headline."""
    if not text:
        return 0.0
    text = str(text)
    scores = []

    zh = _lexicon_score(text, ZH_POS, ZH_NEG)
    if zh is not None:
        scores.append(zh)
    ko = _lexicon_score(text, KO_POS, KO_NEG)
    if ko is not None:
        scores.append(ko)

    latin = _CJK.sub(" ", text)
    if _VADER is not None and re.search(r"[A-Za-z]", latin):
        v = _VADER.polarity_scores(latin)["compound"]
        low = latin.lower()
        boost = _lexicon_score(low, EN_POS, EN_NEG)
        if boost is not None:
            v = max(-1.0, min(1.0, 0.8 * v + 0.6 * boost))
        scores.append(v)

    if not scores:
        return 0.0
    return float(sum(scores) / len(scores))


def direction_label(score: float) -> str:
    if score >= 0.05:
        return "Bullish"
    if score <= -0.05:
        return "Bearish"
    return "Neutral"
