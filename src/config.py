"""Central configuration: assets, sources, keywords, paths.

Everything the pipeline needs to know about *what* to collect lives here so
the rest of the code stays generic.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()
EXA_API_KEY = os.getenv("EXA_API_KEY", "").strip()

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "output"
for _d in (RAW_DIR, PROCESSED_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Assets: 5 per exchange, as suggested by the assignment brief's guidance.
# `keywords` are used to attribute general-channel/forum posts to a ticker
# (ticker code, cashtag, English name, local-language names).
# ---------------------------------------------------------------------------
ASSETS = [
    # --- Hong Kong (Hang Seng) ---
    dict(exchange="HK", ticker="0700.HK", code="0700", name="Tencent Holdings",
         local_name="騰訊", currency="HKD",
         keywords=["0700", "$0700", "Tencent", "腾讯", "騰訊"]),
    dict(exchange="HK", ticker="9988.HK", code="9988", name="Alibaba Group",
         local_name="阿里巴巴", currency="HKD",
         keywords=["9988", "$9988", "Alibaba", "阿里巴巴", "阿里"]),
    dict(exchange="HK", ticker="3690.HK", code="3690", name="Meituan",
         local_name="美團", currency="HKD",
         keywords=["3690", "$3690", "Meituan", "美团", "美團"]),
    dict(exchange="HK", ticker="1810.HK", code="1810", name="Xiaomi",
         local_name="小米", currency="HKD",
         keywords=["1810", "$1810", "Xiaomi", "小米"]),
    dict(exchange="HK", ticker="0005.HK", code="0005", name="HSBC Holdings",
         local_name="滙豐", currency="HKD",
         keywords=["0005", "$0005", "HSBC", "汇丰", "匯豐", "滙豐"]),
    # --- South Korea (KRX) ---
    dict(exchange="KR", ticker="005930.KS", code="005930", name="Samsung Electronics",
         local_name="삼성전자", currency="KRW",
         keywords=["005930", "Samsung Electronics", "삼성전자"]),
    dict(exchange="KR", ticker="000660.KS", code="000660", name="SK Hynix",
         local_name="SK하이닉스", currency="KRW",
         keywords=["000660", "SK Hynix", "SK하이닉스", "하이닉스"]),
    dict(exchange="KR", ticker="035420.KS", code="035420", name="NAVER",
         local_name="네이버", currency="KRW",
         keywords=["035420", "NAVER", "네이버"]),
    dict(exchange="KR", ticker="035720.KS", code="035720", name="Kakao",
         local_name="카카오", currency="KRW",
         keywords=["035720", "Kakao", "카카오"]),
    dict(exchange="KR", ticker="005380.KS", code="005380", name="Hyundai Motor",
         local_name="현대차", currency="KRW",
         keywords=["005380", "Hyundai Motor", "현대자동차", "현대차"]),
]

ASSET_BY_TICKER = {a["ticker"]: a for a in ASSETS}

# ---------------------------------------------------------------------------
# Social sources (from the brief's list; 2 distinct sources per exchange).
# Telegram channels below are public channels with a web preview (t.me/s/…),
# which is exactly what the Apify Telegram actors read as well.
# ---------------------------------------------------------------------------
TELEGRAM_CHANNELS = {
    # Korean retail-stock channels (KR)
    "KR": ["jstockclass", "smallcap", "Herbstock"],
    # Hong Kong (HK): an active HK news channel.  Dedicated public HK
    # *stock-discussion* Telegram channels effectively do not exist (many
    # candidates probed 2026-11-06 — dead or preview-less); LIHKG is the
    # real HK forum source.  See README section 5.
    "HK": ["stheadline"],
}

# LIHKG category ids verified live 2026-11-06: 15 = 財經台 (Finance).
LIHKG_CATEGORY_IDS = [15]

# How far back to collect social posts / news (brief: last 10 days).
LOOKBACK_DAYS = 10
# Price history needed for support/resistance + price features.
PRICE_HISTORY_DAYS = 200

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
