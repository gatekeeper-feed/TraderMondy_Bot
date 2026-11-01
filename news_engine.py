import os
import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

# Expanded News Queries covering Crypto Security, Geopolitics, Energy & Equities
ENHANCED_NEWS_QUERIES = {
    "Crypto & Security": "Binance OR Bybit OR hack OR exploit OR crypto security OR ETF",
    "Geopolitics & War": "Strait of Hormuz OR Red Sea OR tanker OR war OR missile OR tariffs OR sanction",
    "Macro & Crude": "crude oil OR brent OR OPEC OR US CPI OR Federal Reserve OR inflation OR yields",
    "Indian Equities": "Nifty 50 OR Sensex OR Bank Nifty OR RBI OR FII DII",
}

# Free RSS feeds for the pre/post market reports
FREE_RSS_SOURCES = [
    {"url": "https://cointelegraph.com/rss", "source": "CoinTelegraph"},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "CoinDesk"},
    {"url": "https://decrypt.co/feed", "source": "Decrypt Media"},
]


def fetch_all_news():
    """Headlines for the pre-market and post-market reports."""
    headlines = []
    seen = set()

    news_api_key = os.getenv("NEWS_API_KEY")
    if news_api_key:
        for label, query in ENHANCED_NEWS_QUERIES.items():
            try:
                res = requests.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": query, "sortBy": "publishedAt", "pageSize": 5, "apiKey": news_api_key},
                    timeout=8,
                )
                if res.status_code == 200:
                    for art in res.json().get("articles", []):
                        title = art.get("title")
                        if title and title not in seen:
                            seen.add(title)
                            headlines.append(title)
            except Exception as e:
                print(f"NewsAPI error for {label}: {e}")

    for feed in FREE_RSS_SOURCES:
        try:
            res = requests.get(feed["url"], timeout=6, headers={"User-Agent": "TraderMondyBot/1.0"})
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:4]:
                    title_elem = item.find("title")
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text
                        if title not in seen:
                            seen.add(title)
                            headlines.append(title)
        except Exception as e:
            print(f"RSS error for {feed['source']}: {e}")

    return headlines[:12]


# ---------------- Breaking news watch ----------------

WATCH_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Decrypt", "https://decrypt.co/feed"),
]

GOOGLE_QUERIES = [
    "Binance OR Bybit OR Coinbase OR OKX hack OR exploit OR stolen when:1h",
    "crypto exchange hacked OR exploit OR drained when:1h",
    "Strait of Hormuz OR missile OR war OR airstrike when:3h",
    "tariff OR sanctions OR Federal Reserve emergency when:3h",
    "OPEC OR crude oil plunge OR crash when:3h",
    "RBI OR Sensex OR Nifty crash OR circuit when:3h",
    "gold price record OR plunge when:3h",
    "Bitcoin ETF OR SEC bitcoin when:3h",
]

HIGH_PATTERNS = [
    r"\bhack(ed|ers?|s)?\b", r"\bexploit(ed|s)?\b", r"\bdrained\b", r"\bstolen\b",
    r"\bbreach(ed)?\b", r"withdrawals? (suspended|halted|paused)",
    r"(suspends?|halts?|pauses?) withdrawals?", r"\binsolven", r"\bbankrupt",
    r"\bmissile", r"\bairstrikes?\b", r"\binvasion\b", r"\bhormuz\b",
    r"emergency (rate|meeting)", r"rate (cut|hike)", r"\btariffs?\b", r"\bsanctions?\b",
    r"circuit breaker", r"trading halt", r"\bcrash(es|ed)?\b", r"\bplunge[sd]?\b",
    r"\bplummet", r"record high", r"etf (approv|reject|delay)", r"sec (sues|charges)",
    r"\bdefault\b", r"\bceasefire\b",
]

ASSET_PATTERNS = [
    r"bitcoin", r"\bbtc\b", r"crypto", r"ethereum", r"binance", r"bybit", r"coinbase",
    r"\bokx\b", r"\bgold\b", r"\bsilver\b", r"\boil\b", r"crude", r"opec", r"nifty",
    r"sensex", r"\brbi\b", r"\bfed\b", r"federal reserve", r"dollar", r"rupee",
    r"stock", r"market", r"hormuz", r"treasury", r"yields", r"exchange",
]


def _age_ok(pub, hours=4):
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt <= timedelta(hours=hours)
    except Exception:
        return True


def _read_feed(url, source):
    out = []
    try:
        res = requests.get(url, timeout=8, headers={"User-Agent": "TraderMondyBot/1.0"})
        if res.status_code != 200:
            return out
        root = ET.fromstring(res.content)
        for item in root.findall(".//item")[:15]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title and _age_ok(item.findtext("pubDate")):
                out.append({"title": title, "link": link, "source": source})
    except Exception as e:
        print(f"Feed error {source}: {e}")
    return out


def fetch_breaking():
    """Important, recent, market-relevant headlines (no AI, completely free)."""
    items = []
    for name, url in WATCH_FEEDS:
        items += _read_feed(url, name)
    for q in GOOGLE_QUERIES:
        gurl = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        items += _read_feed(gurl, "Google News")

    result, ids = [], set()
    for it in items:
        t = it["title"].lower()
        if not any(re.search(p, t) for p in HIGH_PATTERNS):
            continue
        if not any(re.search(p, t) for p in ASSET_PATTERNS):
            continue
        key = hashlib.md5(re.sub(r"\W+", " ", t).strip()[:80].encode()).hexdigest()[:12]
        if key in ids:
            continue
        ids.add(key)
        it["id"] = key
        result.append(it)
    return result
