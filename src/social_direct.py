"""Direct (no-account) social providers.

These read the SAME public surfaces the Apify actors read — Telegram's
public channel preview (t.me/s/…), Naver Finance's per-ticker discussion
boards and LIHKG's public category feed — so the pipeline can run before
the Apify account/token exists.  Every row is stamped fetch_mode="direct"
so provenance is never ambiguous; the Apify providers in social_apify.py
produce the identical schema with fetch_mode="apify".
"""
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import (ASSETS, LIHKG_CATEGORY_IDS, LOOKBACK_DAYS,
                     TELEGRAM_CHANNELS, USER_AGENT)

POST_COLUMNS = ["exchange", "source", "ticker", "published_at", "text",
                "author", "likes", "reposts", "views", "followers", "url",
                "fetch_mode"]

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def _get(url, **kw):
    """GET with one retry — the network path to these hosts is flaky."""
    last = None
    for attempt in range(2):
        try:
            r = _session.get(url, timeout=30, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _parse_human_count(s: str) -> int:
    """'12.3K' -> 12300, '1.2M' -> 1200000, '345' -> 345."""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    m = re.match(r"([\d.]+)\s*([KM])?", s)
    if not m:
        return 0
    val = float(m.group(1))
    if m.group(2) == "K":
        val *= 1_000
    elif m.group(2) == "M":
        val *= 1_000_000
    return int(val)


def _match_tickers(text: str, exchange: str):
    """Tickers of `exchange` whose keywords appear in `text` (URLs stripped
    first, so a n.news.naver.com link doesn't count as a NAVER mention)."""
    from .sentiment import strip_urls
    text = strip_urls(text)
    hits = []
    low = text.lower()
    for a in ASSETS:
        if a["exchange"] != exchange:
            continue
        for kw in a["keywords"]:
            probe = kw.lower() if kw.isascii() else kw
            hay = low if kw.isascii() else text
            if probe in hay:
                hits.append(a["ticker"])
                break
    return hits


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=POST_COLUMNS)


# ---------------------------------------------------------------------------
# Telegram — public channel previews at t.me/s/<channel>
# ---------------------------------------------------------------------------
def fetch_telegram_channel(channel: str, exchange: str,
                             cutoff: datetime, max_pages: int = 12) -> pd.DataFrame:
    rows = []
    before = None
    seen_ids = set()
    for _ in range(max_pages):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        try:
            html = _get(url).text
        except requests.RequestException:
            break
        soup = BeautifulSoup(html, "lxml")

        followers = 0
        counter = soup.select_one(".tgme_channel_info_counter")
        if counter and counter.select_one(".counter_value"):
            followers = _parse_human_count(counter.select_one(".counter_value").get_text())

        messages = soup.select(".tgme_widget_message")
        if not messages:
            break
        page_ids, oldest, new_on_page = [], None, 0
        for msg in messages:
            post_id = msg.get("data-post", "")
            if "/" in post_id:
                page_ids.append(int(post_id.split("/")[-1]))
            time_el = msg.select_one("time[datetime]")
            if not time_el:
                continue
            ts = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            oldest = ts if oldest is None else min(oldest, ts)
            if ts < cutoff or post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            new_on_page += 1
            text_el = msg.select_one(".tgme_widget_message_text")
            text = text_el.get_text(" ", strip=True) if text_el else ""
            if not text:
                continue
            views_el = msg.select_one(".tgme_widget_message_views")
            views = _parse_human_count(views_el.get_text()) if views_el else 0
            likes = 0
            for r in msg.select(".tgme_widget_message_reaction"):
                likes += _parse_human_count(r.get_text())
            for ticker in _match_tickers(text, exchange):
                rows.append(dict(
                    exchange=exchange, source="Telegram", ticker=ticker,
                    published_at=ts, text=text, author=channel, likes=likes,
                    reposts=0, views=views, followers=followers,
                    url=f"https://t.me/{post_id}" if post_id else url,
                    fetch_mode="direct"))
        if not page_ids or new_on_page == 0:
            break
        # Page messages run oldest->newest; walk back from the oldest id.
        before = min(page_ids)
        if oldest is not None and oldest < cutoff:
            break
        time.sleep(0.4)
    df = pd.DataFrame(rows, columns=POST_COLUMNS)
    return df.drop_duplicates(subset=["url", "ticker"]) if not df.empty else df


def fetch_telegram(exchange: str, cutoff: datetime) -> pd.DataFrame:
    frames = [fetch_telegram_channel(ch, exchange, cutoff)
              for ch in TELEGRAM_CHANNELS.get(exchange, [])]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty()


# ---------------------------------------------------------------------------
# Naver Finance — per-ticker discussion boards (종목토론실)
# ---------------------------------------------------------------------------
def fetch_naver_board(asset: dict, cutoff: datetime,
                      max_pages: int = 40) -> pd.DataFrame:
    """Classic-board HTML parser (titles, author, views, likes per post).

    NOTE (verified live 2026-11-06): Naver's current redesign serves the
    boards as a client-rendered app, so this parser currently finds no
    table and returns nothing.  The app's community API
    (stock.naver.com/api/community/discussion/items/posts/latest) exists
    but returns 500 for every anonymous parameterisation tried — it seems
    to need the app's session context.  The working Naver route is the
    Apify puppeteer provider in social_apify.py.  This parser is kept as
    the reference implementation for the board's fields."""
    rows = []
    code = asset["code"]
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/item/board.naver?code={code}&page={page}"
        try:
            html = _get(url).text
        except requests.RequestException:
            break
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table.type2")
        if table is None:
            break
        page_oldest = None
        for tr in table.select("tr"):
            tds = tr.find_all("td")
            if len(tds) < 6:
                continue
            title_a = tr.select_one("td.title a")
            if title_a is None:
                continue
            date_txt = tds[0].get_text(strip=True)  # 2026.11.06 14:32
            try:
                ts_local = datetime.strptime(date_txt, "%Y.%m.%d %H:%M")
            except ValueError:
                continue
            # KST = UTC+9
            ts = ts_local.replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
            page_oldest = ts if page_oldest is None else min(page_oldest, ts)
            if ts < cutoff:
                continue
            nid = re.search(r"nid=(\d+)", title_a.get("href", ""))
            rows.append(dict(
                exchange="KR", source="Naver Finance boards",
                ticker=asset["ticker"], published_at=ts,
                text=title_a.get_text(strip=True),
                author=tds[2].get_text(strip=True),
                likes=_parse_human_count(tds[5].get_text()),
                reposts=0,
                views=_parse_human_count(tds[3].get_text()),
                followers=0,
                url=("https://finance.naver.com/item/board_read.naver"
                     f"?code={code}&nid={nid.group(1)}") if nid else url,
                fetch_mode="direct"))
        if page_oldest is not None and page_oldest < cutoff:
            break
        time.sleep(0.3)
    return pd.DataFrame(rows, columns=POST_COLUMNS)


def fetch_naver(cutoff: datetime) -> pd.DataFrame:
    frames = [fetch_naver_board(a, cutoff) for a in ASSETS if a["exchange"] == "KR"]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty()


# ---------------------------------------------------------------------------
# LIHKG — public category feed (finance boards) + opening-post text
# ---------------------------------------------------------------------------
def fetch_lihkg(cutoff: datetime) -> pd.DataFrame:
    """Keyword search per HK asset — exactly the brief's 'ticker, cashtag
    and keyword searches'.  Threads are deduplicated by thread_id."""
    import urllib.parse
    headers = {"X-LI-DEVICE": hashlib.md5(b"tzuroni-pipeline").hexdigest(),
               "X-LI-REQUEST-TIME": str(int(time.time())),
               "Referer": "https://lihkg.com/"}
    rows, seen = [], set()
    for asset in ASSETS:
        if asset["exchange"] != "HK":
            continue
        queries = [asset["code"], asset["local_name"], asset["name"]]
        for q in queries:
            # No category filter: HK single-stock talk is spread across
            # boards, and the finance board's own threads skew old/US.
            url = ("https://lihkg.com/api_v2/thread/search?q="
                   + urllib.parse.quote(q)
                   + "&page=1&count=30&sort=desc_create_time")
            try:
                data = _get(url, headers=headers).json()
            except (requests.RequestException, ValueError):
                continue
            items = (data.get("response") or {}).get("items") or []
            for it in items:
                tid = it.get("thread_id")
                if tid in seen:
                    continue
                # A thread counts when it was created in the window or was
                # actively replied to in the window; it is timestamped by
                # whichever of the two is in-window (creation preferred).
                created = datetime.fromtimestamp(it.get("create_time", 0),
                                                 tz=timezone.utc)
                replied = datetime.fromtimestamp(it.get("last_reply_time", 0),
                                                 tz=timezone.utc)
                if created >= cutoff:
                    ts = created
                elif replied >= cutoff:
                    ts = replied
                else:
                    continue
                seen.add(tid)
                rows.append(dict(
                    exchange="HK", source="LIHKG", ticker=asset["ticker"],
                    published_at=ts, text=it.get("title", ""),
                    author=(it.get("user_nickname") or ""),
                    likes=int(it.get("like_count") or 0),
                    reposts=int(it.get("no_of_reply") or 0),
                    views=int(it.get("no_of_views") or 0), followers=0,
                    url=f"https://lihkg.com/thread/{tid}",
                    fetch_mode="direct"))
            time.sleep(0.3)
    return pd.DataFrame(rows, columns=POST_COLUMNS)


def fetch_all_direct() -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    frames = [fetch_telegram("HK", cutoff), fetch_telegram("KR", cutoff),
              fetch_naver(cutoff), fetch_lihkg(cutoff)]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty()
