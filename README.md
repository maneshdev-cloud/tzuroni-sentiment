# Sentiment → Next-Day Price Prediction Pipeline
### Hang Seng (HK) & KRX (KR) — CrowdWisdomTrading internship assignment

**Author:** Manesh Sunil Jadhav — final-year Diploma in AI & ML,
Government Polytechnic Mumbai.
**Assignment:** TZURONI LTD (CrowdWisdomTrading) — *AI Agent Development*
internship assessment, received via Internshala, November 2026.

A Python pipeline that collects social-media sentiment and news for
5 Hong Kong and 5 Korean stocks, scores it locally, aligns it with daily
price bars, trains a model to predict the **next day's (n+1) price and
direction**, validates it with walk-forward out-of-sample backtesting, and
renders a visual HTML report ranking every ticker by mentions, sentiment
and predicted direction.

**Results at a glance (reference run, 6 Nov 2026, direct mode):**
walk-forward out-of-sample backtest on 35 test rows — HK direction accuracy
73% (equals its majority baseline), KR 30% (below baseline). Reported
honestly with baselines in §6, because a pipeline you can trust starts
with numbers you can check.

---

## 1. How each brief requirement is implemented

| Brief requirement | Where / how |
|---|---|
| Python sentiment pipeline predicting price at n+1 from ≥ 2 sentiment sources | `run_pipeline.py`; model in `src/model.py` |
| Scrape social posts with **Apify** | `src/social_apify.py` — Telegram actor `chorelet/telegram-channel-posts-scraper`; Naver boards via `apify/puppeteer-scraper` (see §5 for account status) |
| News sentiment with **Exa** | `src/news.py::fetch_exa` (POST `api.exa.ai/search`, category=news) |
| 2 different listed sources per exchange | HK: **LIHKG** + **Telegram**. KR: **Naver Finance boards** + **Telegram** (§5 documents the Naver caveat) |
| 5 assets per exchange | HK: Tencent 0700.HK, Alibaba 9988.HK, Meituan 3690.HK, Xiaomi 1810.HK, HSBC 0005.HK. KR: Samsung Electronics 005930.KS, SK Hynix 000660.KS, NAVER 035420.KS, Kakao 035720.KS, Hyundai Motor 005380.KS (`src/config.py`) |
| Ticker / cashtag / keyword searches, last 10 days | LIHKG keyword search per asset (code, local name, English name); Telegram channel posts keyword-attributed; Naver boards are per-ticker by construction |
| Extract timestamps (UTC), text, engagement, author followers; align with price bars | Post schema in `src/social_direct.py`; UTC normalisation on ingest; trading-day alignment in `src/features.py` |
| Recent news per asset to complement social sentiment | Exa (primary) / labelled Google News RSS fallback (`src/news.py`) |
| Per ticker: ticker, asset name, current price, sentiment, direction, position if any, support/resistance | `output/ticker_summary.csv` + report cards (`src/report.py`); levels in `src/prices.py` |
| Visual report ranking tickers by mentions / sentiment / direction per exchange | `output/report.html` (self-contained; charts embedded) |
| Predict price at n+1 and **check the results** | Walk-forward backtest → `output/backtest.csv`, `output/metrics.json`; live forecasts → `output/predictions.csv` |
| Rigorous out-of-sample validation | Walk-forward only: every test day is predicted by a model trained strictly on earlier days; no shuffling (`src/model.py`) |
| Submission by email with repo link + Apify/Exa tokens & actor IDs | `SUBMISSION_NOTES.md` (tokens live only in `.env`, never in this repo) |

## 2. Pipeline stages

```
prices ─┐
social ─┼─> sentiment scoring ─> daily features ─> walk-forward backtest
news ───┘                                        └> live n+1 predictions
                                                        │
                                              visual HTML report
```

## 3. Setup & run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # add APIFY_TOKEN and EXA_API_KEY (free tiers)
.venv/bin/python run_pipeline.py            # auto: Apify/Exa if tokens exist
.venv/bin/python run_pipeline.py --mode direct   # force no-account providers
.venv/bin/python -m pytest tests/ -q
```

Outputs land in `output/` (`report.html`, `predictions.csv`, `backtest.csv`,
`metrics.json`, `ticker_summary.csv`); raw and processed data in `data/`.

## 4. Method notes

* **Sentiment** (`src/sentiment.py`) — fully local and auditable. English
  text: VADER, nudged by a small finance lexicon (*beat, downgrade,
  selloff…*). Chinese/Korean text: hand-built bullish/bearish market-term
  lexicons （騰訊-style HK posts and Korean board titles included). Scores in
  [-1, 1]; daily aggregates are engagement-weighted
  (weight = 1 + log1p(views) + likes).
* **Alignment** — a post belongs to trading day *t* if its UTC date falls in
  (previous trading day, *t*]; weekend posts roll into Monday. No feature
  uses information from after day *t*'s close.
* **Model** — one pooled model per exchange (5 tickers share it; per-ticker
  models on 10 days of sentiment would be noise). Direction: logistic
  regression. Price: ridge regression on next-day return → predicted close =
  close × (1 + return). Baselines (majority class; naive "tomorrow = today")
  are reported next to every metric.
* **Support / resistance** — classic pivot S1/R1 from the previous session
  plus 20-day swing low/high.
* **"Position if any"** — a transparent rule on top of the model:
  P(up) ≥ 0.60 and sentiment ≥ +0.05 → *Long bias*; P(up) ≤ 0.40 and
  sentiment ≤ −0.05 → *Avoid / short bias*; otherwise *Neutral*. It is a
  model stance for the assignment, **not investment advice**.

## 5. Data provenance & honest limitations

Every collected row is stamped with how it was fetched
(`fetch_mode` / `provider` columns) — nothing is silently mixed.

* **Accounts — Exa ✅, Apify pending.** The Exa free account exists and its
  key is in `.env` (never committed); the Apify signup is still open on my
  side, so no Apify token exists yet. The code paths are implemented
  (`src/social_apify.py`, Exa in `src/news.py`); `SUBMISSION_NOTES.md`
  has the activation steps. The reference run below therefore used
  **direct mode** (below) and the report says so — one token plugs the
  Apify path straight in.
* **Direct mode reads the same public surfaces the actors read** —
  Telegram's public channel previews (`t.me/s/…`, the exact pages the
  Apify Telegram actors parse), LIHKG's public JSON API (the endpoints its
  own web app calls), and Google News RSS in place of Exa. All data is
  real; only the transport differs.
* **Naver Finance boards (KR source 2)** — Naver's current redesign serves
  the boards as a client-rendered app: the classic HTML table is gone.
  The app's own community API route exists
  (`stock.naver.com/api/community/discussion/items/posts/latest`) but
  answered every anonymous parameterisation with server errors (500) —
  it appears to need the app's session context. The working route is the
  Apify puppeteer provider (rendered DOM); its pageFunction is written
  but **unverified** until the Apify account exists. In the direct run
  below, KR social data therefore comes from Telegram alone — stated
  plainly rather than papered over.
* **LIHKG volume is sparse** — HK single-stock discussion is thin and
  lives in long threads; the finance-board keyword search yields a handful
  of fresh threads per ticker in 10 days. Counts in the report are the
  real counts.
* **Telegram in HK is effectively empty** — a dozen candidate HK channels
  were probed: the one "HK stocks" channel found is dead, and the HK news
  outlets' channels expose no public post preview. One active HK news
  channel (`stheadline`) is configured; it produced 0 of-our-tickers
  posts in this window. The Telegram code path is proven by the KR leg
  (22 posts). HK's forum leg is LIHKG, as the brief's source list
  anticipates (LIHKG is its first HK entry).
* **Prices** — yfinance is the default provider; in this sandbox Yahoo
  Finance was unreachable through the egress proxy (timeouts), so the run
  used the implemented fallback: Naver's public stock API (same OHLCV
  fields, per-row `price_source` column records this).
* **Sample size** — 10 days of sentiment ⇒ the backtest has only a few
  dozen test rows. Metrics are reported with baselines so they can be
  judged honestly; this validates the pipeline, it does not prove an edge.

## 6. Results of the reference run (2026-11-06, direct mode)

**Data collected**

| Feed | Result |
|---|---|
| Prices | 2,000 daily bars (10 tickers × 200 days, 2026-01-13 → 2026-11-06) via the Naver-API fallback (Yahoo unreachable from this sandbox) |
| Social posts (10 days) | **25 posts** — HK: LIHKG 3 (Tencent 1, Meituan 2); KR: Telegram 22 (Samsung Electronics 9, SK Hynix 9, Hyundai Motor 3, NAVER 1, Kakao 0) |
| News items (10 days) | **240** via the Google News RSS fallback (per ticker: SK Hynix 65, Samsung 33, Tencent 30, Alibaba 28, Meituan 23, HSBC 23, Xiaomi 19, Kakao 13, NAVER 4, Hyundai 2) |
| Feature matrix | 85 ticker-days from 2026-10-27 |

**Backtest — walk-forward, out-of-sample**

| Scope | Test rows | Direction accuracy | Majority baseline | Price MAE (model) | Price MAE (naive) |
|---|---|---|---|---|---|
| HK | 15 | 73% | 73% | 7.68 | 5.19 |
| KR | 20 | 30% | 60% | 26,615 | 20,645 |
| All | 35 | 49% | 54% | 15,212* | 11,799 |

\* blended across HKD/KRW scales — per-exchange rows are the meaningful ones.

**Honest reading:** on this 10-day sample the model shows **no tradable
edge** — HK accuracy equals its majority-class baseline, KR is worse than
baseline, and price MAE loses to "tomorrow = today" on both exchanges.
Social features were zero on most ticker-days (the feeds above are
genuinely sparse), so the model leaned on price features. This is the
real result of a correctly-built pipeline on a small window, reported
with its baselines rather than dressed up. The n+1 machinery, validation
and reporting are the deliverable; a production version would need
months of sentiment history (the Apify path + scheduled daily runs).

**Live n+1 predictions** (next trading day after the last bar)

| Ticker | Last close | Predicted next close | Direction | P(up) |
|---|---|---|---|---|
| Tencent 0700.HK | 419.80 | 440.32 | Up | 0.999 |
| Alibaba 9988.HK | 104.90 | 110.24 | Up | 0.997 |
| Meituan 3690.HK | 80.40 | 85.65 | Up | 0.998 |
| Xiaomi 1810.HK | 30.38 | 32.04 | Up | 0.979 |
| HSBC 0005.HK | 137.50 | 142.96 | Up | 0.973 |
| Samsung Elec. 005930.KS | 193,500 | 186,923 | Down | 0.420 |
| SK Hynix 000660.KS | 1,176,000 | 1,120,343 | Down | 0.328 |
| NAVER 035420.KS | 188,600 | 195,417 | Up | 0.597 |
| Kakao 035720.KS | 32,000 | 33,146 | Up | 0.676 |
| Hyundai Motor 005380.KS | 281,000 | 286,772 | Up | 0.589 |

(HK probabilities are near-saturated — a known artefact of logistic
regression on a tiny, near-separable training window; treat the
*direction* as the signal, not the third decimal. Predictions are saved
in `output/predictions.csv` so they can be checked against the actual
next close — "check your results".)

## 7. Repository layout

```
run_pipeline.py        entry point (stages, provenance, CLI)
src/config.py          assets, sources, keywords, env
src/prices.py          yfinance + Naver-API fallback, support/resistance
src/social_apify.py    Apify providers (Telegram actor, Naver puppeteer)
src/social_direct.py   direct providers (Telegram preview, LIHKG, Naver classic)
src/news.py            Exa provider + Google News RSS fallback
src/sentiment.py       EN/ZH/KO sentiment scoring (local, documented)
src/features.py        trading-day alignment & feature build
src/model.py           walk-forward validation + live n+1 predictions
src/report.py          visual HTML report
tests/                 sentiment / levels / no-lookahead tests
SUBMISSION_NOTES.md    what to email, actor IDs, account activation steps
```
