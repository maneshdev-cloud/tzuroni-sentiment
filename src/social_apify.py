"""Apify providers — the brief's primary scraping route.

Actors used (recorded in SUBMISSION_NOTES.md):
* Telegram ......... chorelet/telegram-channel-posts-scraper
                     (reads the same public t.me/s previews as the direct
                     provider; input: {"channels": [...]})
* Naver boards ..... apify/puppeteer-scraper.  Naver's 2025 redesign made
                     the discussion boards client-rendered, so a real
                     browser render is the reliable route; the pageFunction
                     below extracts post title/author/date from the
                     rendered discussion list.  NOTE: this pageFunction is
                     written against the rendered DOM structure and is
                     UNVERIFIED — it needs one live run (Apify account) to
                     confirm the selectors; see SUBMISSION_NOTES.md.

Requires APIFY_TOKEN in .env.  Without a token these raise RuntimeError and
run_pipeline.py falls back to the direct providers, stamping rows
fetch_mode="direct" so the two are never confused.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import APIFY_TOKEN, ASSETS, LOOKBACK_DAYS, TELEGRAM_CHANNELS
from .social_direct import POST_COLUMNS, _empty, _match_tickers

TELEGRAM_ACTOR = "chorelet/telegram-channel-posts-scraper"
CHEERIO_ACTOR = "apify/cheerio-scraper"
PUPPETEER_ACTOR = "apify/puppeteer-scraper"


def _client():
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN is not set in .env")
    from apify_client import ApifyClient
    return ApifyClient(APIFY_TOKEN)


def fetch_telegram_apify(exchange: str, cutoff: datetime) -> pd.DataFrame:
    client = _client()
    channels = TELEGRAM_CHANNELS.get(exchange, [])
    if not channels:
        return _empty()
    run_input = {
        "channels": channels,
        "onlyPostsNewerThan": cutoff.strftime("%Y-%m-%d"),
        "maxPostsPerChannel": 300,
    }
    run = client.actor(TELEGRAM_ACTOR).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    rows = []
    for it in items:
        if it.get("type") and it.get("type") != "post":
            continue
        text = it.get("text") or ""
        if not text:
            continue
        ts = it.get("date")
        ts = (datetime.fromisoformat(ts.replace("Z", "+00:00"))
              if isinstance(ts, str) else None)
        if ts is None or ts < cutoff:
            continue
        for ticker in _match_tickers(text, exchange):
            rows.append(dict(
                exchange=exchange, source="Telegram", ticker=ticker,
                published_at=ts, text=text,
                author=it.get("channel") or "",
                likes=int(it.get("reactionsTotal") or 0), reposts=0,
                views=int(it.get("views") or 0),
                followers=int(it.get("channelSubscribers") or 0),
                url=it.get("url") or "", fetch_mode="apify"))
    return pd.DataFrame(rows, columns=POST_COLUMNS)


# Page function executed by apify/puppeteer-scraper on the *rendered*
# Naver discussion page: collect post links inside the discussion list and
# pull the date/views text from their surrounding row element.
_NAVER_PAGE_FUNCTION = """
async function pageFunction(context) {
  const { page, request } = context;
  await page.waitForSelector('[class*="DiscussionPage"]', { timeout: 20000 })
    .catch(() => {});
  await new Promise(r => setTimeout(r, 2500));
  const rows = await page.evaluate(() => {
    const out = [];
    const links = document.querySelectorAll('a[href*="/discussion/"]');
    links.forEach(a => {
      const title = (a.textContent || '').trim();
      if (!title || title.length < 2) return;
      let row = a;
      for (let i = 0; i < 4 && row.parentElement; i++) row = row.parentElement;
      const text = (row.textContent || '').replace(/\\s+/g, ' ');
      const dm = text.match(/(\\d{4}\\.\\d{2}\\.\\d{2}\\s+\\d{2}:\\d{2})/);
      out.push({ title, href: a.href, date: dm ? dm[1] : '', rowText: text.slice(0, 200) });
    });
    return out;
  });
  return rows.map(r => ({ ...r, ticker: request.userData.ticker }));
}
"""


def fetch_naver_apify(cutoff: datetime) -> pd.DataFrame:
    client = _client()
    urls = []
    for a in ASSETS:
        if a["exchange"] != "KR":
            continue
        urls.append({"url": f"https://finance.naver.com/item/board.naver"
                            f"?code={a['code']}&page=1",
                     "userData": {"ticker": a["ticker"], "code": a["code"]}})
    run = client.actor(PUPPETEER_ACTOR).call(run_input={
        "startUrls": urls, "pageFunction": _NAVER_PAGE_FUNCTION,
        "proxyConfiguration": {"useApifyProxy": True}})
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    rows = []
    for it in items:
        try:
            ts_local = datetime.strptime(it.get("date", ""), "%Y.%m.%d %H:%M")
        except ValueError:
            continue
        ts = ts_local.replace(
            tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
        if ts < cutoff:
            continue
        rows.append(dict(
            exchange="KR", source="Naver Finance boards",
            ticker=it.get("ticker", ""),
            published_at=ts, text=it.get("title", ""),
            author="", likes=0, reposts=0, views=0, followers=0,
            url=it.get("href", ""), fetch_mode="apify"))
    df = pd.DataFrame(rows, columns=POST_COLUMNS)
    return df[df["ticker"] != ""] if not df.empty else df


def fetch_all_apify() -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    frames = [fetch_telegram_apify("HK", cutoff),
              fetch_telegram_apify("KR", cutoff),
              fetch_naver_apify(cutoff)]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty()
