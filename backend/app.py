import os, math, json, time, datetime
from typing import Dict, Any
import pandas as pd
import numpy as np
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import feedparser
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

# One-time download (free)
try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon')

# Use a polite SEC user agent (replace with your contact)
SEC_HEADERS = {
    "User-Agent": "OpenResearchPWA/1.0 (contact: you@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
}

app = FastAPI(title="Open Research Backend", version="1.0.0")

# CORS: open for easy testing (you can restrict later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def now_utc_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def restricted_link(url: str) -> Dict[str, str]:
    return {"restricted; visit link": url}

async def fetch_json(client: httpx.AsyncClient, url: str, headers: Dict[str, str] | None = None) -> Any:
    try:
        r = await client.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return restricted_link(url)
        ct = r.headers.get("content-type","")
        if "application/json" in ct or url.endswith(".json"):
            return r.json()
        return {"url": url, "content": r.text[:50000]}
    except Exception:
        return restricted_link(url)

def last_12m_dates():
    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(days=365)
    return start.date().isoformat(), end.date().isoformat()

async def module1_facts(ticker: str) -> Dict[str, Any]:
    start_date, end_date = last_12m_dates()
    out: Dict[str, Any] = {
        "ticker": ticker.upper(),
        "window": {"from": start_date, "to": end_date},
        "sources_used": []
    }

    async with httpx.AsyncClient() as client:
        # 1) Company profile & quotes (Yahoo Finance via yfinance)
        yf_tkr = yf.Ticker(ticker)
        info = {}
        try:
            info = yf_tkr.info or {}
        except Exception:
            info = {}
        out["company_info"] = {
            "shortName": info.get("shortName"),
            "longName": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
            "country": info.get("country"),
        }
        out["sources_used"].append(f"https://finance.yahoo.com/quote/{ticker.upper()}")

        # 2) Last 4 quarters (revenue/net income if available)
        try:
            q = yf_tkr.quarterly_financials
            rows = {}
            if isinstance(q, pd.DataFrame) and not q.empty:
                qt = q.T
                for d, row in qt.tail(4).iterrows():
                    rows[str(d.date())] = {
                        "Revenue": row.get("Total Revenue", None),
                        "NetIncome": row.get("Net Income", None)
                    }
            out["last_4_quarters"] = rows
        except Exception:
            out["last_4_quarters"] = {}

        # 3) Ratios snapshot
        ratios = {}
        keys = ["trailingPE","forwardPE","priceToBook","returnOnEquity","profitMargins","debtToEquity","operatingMargins"]
        for k in keys:
            v = info.get(k)
            ratios[k] = float(v) if v is not None else None
        out["financial_ratios"] = ratios

        # 4) Filings link (EDGAR search page or company IR page)
        if ticker.upper() == "INTC":
            filings_url = "https://www.intc.com/filings-reports/all-sec-filings"
            edgar = await fetch_json(client, filings_url)
        else:
            filings_url = f"https://www.sec.gov/edgar/search/#/q={ticker.upper()}&category=custom&forms=10-K,10-Q,8-K"
            edgar = await fetch_json(client, filings_url, headers=SEC_HEADERS)
        out["edgar_filings"] = edgar

        # 5) News headlines (Google News RSS)
        query = f"{ticker} when:365d"
        rss_url = f"https://news.google.com/rss/search?q={httpx.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        rss = feedparser.parse(rss_url)
        headlines = []
        for e in rss.entries[:30]:
            headlines.append({
                "title": e.title,
                "link": e.link,
                "published": getattr(e, "published", None)
            })
        out["news_headlines"] = headlines
        out["sources_used"].append("https://news.google.com/rss/")

        # 6) Light examples for corporate actions / leadership (for INTC demo)
        if ticker.upper() == "INTC":
            out.setdefault("corporate_actions", []).append({
                "item": "Example: Noted major partnership and restructuring in last 12 months (see news/filings).",
                "sources": [
                    "https://www.intc.com/filings-reports/all-sec-filings",
                    f"https://news.google.com/search?q={ticker}"
                ]
            })
            out["leadership"] = {
                "change": "Example: leadership changes referenced in public news.",
                "sources": [f"https://news.google.com/search?q={ticker}+leadership"]
            }
            out["dividends"] = {
                "status": "Check company IR or Yahoo 'Dividends' tab for current status.",
                "sources": [f"https://finance.yahoo.com/quote/{ticker}/history?p={ticker}"]
            }

    return out

def module2_financial_score(m1: Dict[str,Any]) -> tuple[int, Dict[str, Any]]:
    ratios = m1.get("financial_ratios", {})
    subscores = {}

    # Profitability/margins
    pm = [x for x in (ratios.get("profitMargins"), ratios.get("operatingMargins"), ratios.get("returnOnEquity")) if x is not None]
    subscores["profitability"] = max(0, min(100, int(50 + 20*len(pm) + 100*(np.nanmean(pm) if pm else -0.2))))

    # Growth: simple revenue trend if available
    l4q = m1.get("last_4_quarters", {})
    revs = []
    for _, v in l4q.items():
        if isinstance(v, dict) and v.get("Revenue") is not None:
            revs.append(v["Revenue"])
    if len(revs) >= 2 and revs[0]:
        growth = (revs[-1]-revs[0])/abs(revs[0])
    else:
        growth = -0.05
    subscores["growth"] = max(0, min(100, int(50 + 200*growth)))

    # Balance sheet: debt/equity lower is better
    d2e = ratios.get("debtToEquity")
    subscores["balance_sheet"] = 50 if d2e is None else max(0, min(100, int(80 - min(d2e, 200)/2)))

    # Cash flow quality: placeholder 50 without CF statements
    subscores["cashflow_quality"] = 50

    # Valuation: rough P/B and P/E check
    pb = ratios.get("priceToBook")
    pe = ratios.get("trailingPE") or ratios.get("forwardPE")
    val = 50
    if pb is not None:
        val += int(max(-20, min(20, 10*(1.5 - min(pb,5)))))
    if pe is not None and pe > 0:
        val += int(max(-20, min(20, 5*(12 - min(pe,40))/12)))
    subscores["valuation"] = max(0, min(100, val))

    subscores["industry_position"] = 50
    subscores["regulatory_signals"] = 50

    weights = {
        "profitability": 0.25,
        "growth": 0.2,
        "balance_sheet": 0.15,
        "cashflow_quality": 0.1,
        "valuation": 0.2,
        "industry_position": 0.05,
        "regulatory_signals": 0.05
    }
    score = int(sum(subscores[k]*w for k,w in weights.items()))
    return score, subscores

def module3_exogenous_score(m1: Dict[str,Any]) -> tuple[int, Dict[str, Any]]:
    kw_pos = ["subsidy","grant","government stake","partnership","investment","CHIPS","incentive"]
    kw_neg = ["tariff","sanction","ban","strike","flood","earthquake","war","export control","geopolitics","conflict","typhoon","hurricane"]
    news = m1.get("news_headlines", [])
    pos = sum(any(k.lower() in (n.get("title") or "").lower() for k in kw_pos) for n in news)
    neg = sum(any(k.lower() in (n.get("title") or "").lower() for k in kw_neg) for n in news)
    raw = min(10, max(-20, pos - 2*neg))  # −20 … +10
    rescaled = int((raw + 20) * (100/30))  # → 0 … 100
    return rescaled, {"raw": raw, "pos_hits": pos, "neg_hits": neg}

def module4_behavioral_score(m1: Dict[str,Any]) -> tuple[int, Dict[str, Any]]:
    sia = SentimentIntensityAnalyzer()
    news = m1.get("news_headlines", [])
    if not news:
        return 50, {"sentiment": 0.0}
    scores = [sia.polarity_scores(n["title"])["compound"] for n in news if n.get("title")]
    if not scores:
        return 50, {"sentiment": 0.0}
    avg = float(np.mean(scores))
    sent = int((avg + 1) * 50)  # −1..+1 → 0..100
    score = int(0.7*sent + 0.3*55)  # blend with a discipline baseline
    return score, {"avg_compound": avg, "headline_count": len(scores)}

@app.get("/api/research")
async def research(ticker: str = Query(..., min_length=1, max_length=10)):
    """
    Returns facts + scores + verdict for a ticker using only free/public sources.
    If any source is restricted/paywalled, returns: {"restricted; visit link": "<URL>"} for that item.
    """
    t = ticker.upper().strip()
    m1 = await module1_facts(t)
    fin_score, fin_detail = module2_financial_score(m1)
    exo_score, exo_detail = module3_exogenous_score(m1)
    beh_score, beh_detail = module4_behavioral_score(m1)

    overall = int(0.65*fin_score + 0.15*exo_score + 0.20*beh_score)
    rating = "Buy" if overall >= 70 else ("Hold" if overall >= 50 else "Sell")

    result = {
        "as_of": now_utc_iso(),
        "ticker": t,
        "module_1_facts": m1,
        "module_2_financial_score": {"score": fin_score, "detail": fin_detail},
        "module_3_exogenous_score": {"score_rescaled_0to100": exo_score, "detail": exo_detail},
        "module_4_behavioral_score": {"score": beh_score, "detail": beh_detail},
        "overall": {"score": overall, "rating": rating}
    }
    return result

