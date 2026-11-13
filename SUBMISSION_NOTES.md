# Submission notes — TZURONI / CrowdWisdomTrading assignment

**Status: SUBMITTED 13 Nov 2026 (as-is).** Reference run is direct mode
(no Apify token yet — see below); Exa key obtained and shared in the
submission email for reproducibility.

## Where it goes

* **To:** gilad@crowdwisdomtrading.com (Gilad, CrowdWisdomTrading CEO)
* **Deadline:** Internshala states **13 Nov 2026**; the brief's own
  timeline says "5 days after receiving" (≈ **11 Nov 2026**) — aim for
  11 Nov.
* **Must include (per the brief):**
  1. Link to the GitHub repository (after push to
     `github.com/maneshdev-cloud` — repo not pushed yet).
  2. The **Apify and Exa tokens** and the **actor IDs** used, so they can
     reproduce the pipeline. Tokens live ONLY in `.env` (gitignored) —
     copy them from there into the email at send time; never commit them.

## Actor IDs used by the Apify providers (`src/social_apify.py`)

| Purpose | Actor ID |
|---|---|
| Telegram channel posts (HK + KR) | `chorelet/telegram-channel-posts-scraper` |
| Naver Finance discussion boards (rendered) | `apify/puppeteer-scraper` |

LIHKG is consumed through its public JSON API directly (the endpoints the
LIHKG web app itself calls) — no Apify actor exists for it; the code path
is identical in both modes. News uses the Exa REST API
(`https://api.exa.ai/search`) — no actor involved.

## ⚠️ Apify activation still open (Exa done)

The Exa free account is created and its key is in `.env`. The Apify
signup is still open, so the reference run used the direct providers +
Google News RSS fallback, all stamped as such.

To activate the full Apify path (≈5 minutes):

1. Sign up free at **apify.com** with `maneshdeveloper@gmail.com`
   (complete any email verification).
2. Apify: Console → Settings → Integrations → copy the API token.
3. Paste it into `.env` (`APIFY_TOKEN=…`).
4. Re-run: `.venv/bin/python run_pipeline.py --mode apify`
   → regenerates all outputs with `fetch_mode="apify"` and Exa news.
   Sanity-check `output/report.html` (provenance banner should say
   apify / exa) and `output/metrics.json`.

## Draft submission email (fill the two blanks at send time)

> Subject: AI Agents Developer Intern — Assignment Submission — Manesh Jadhav
>
> Hi Gilad,
>
> Thank you for the assignment. I have built a Python sentiment pipeline
> that predicts next-day prices for 5 Hang Seng and 5 KRX assets using two
> social sources per exchange (LIHKG + Telegram for HK; Naver Finance
> boards + Telegram for KR) plus news sentiment, with walk-forward
> out-of-sample validation and a visual report ranking tickers by
> mentions, sentiment and direction.
>
> Repository: https://github.com/maneshdev-cloud/tzuroni-sentiment
> Report: `output/report.html` in the repo (self-contained).
>
> One honest note on provenance: the Apify signup step is still open on my
> side, so this run pulled social data through the direct providers (LIHKG
> public API + Telegram) rather than Apify actors, and news through the Google
> News RSS fallback. The pipeline is built so the Apify/Exa path plugs in with
> one token — happy to re-run it that way if you'd like.
>
> For reproducibility, as requested:
> * Apify token: not obtained yet (see note above)
> * Exa API key: <FROM .env>
> * Apify actor IDs: `chorelet/telegram-channel-posts-scraper` (Telegram),
>   `apify/puppeteer-scraper` (Naver boards)
>
> Setup is one command (`python run_pipeline.py`) — details in the README.
>
> Thanks again,
> Manesh Sunil Jadhav
> Final-year AI & ML Diploma, Government Polytechnic Mumbai
