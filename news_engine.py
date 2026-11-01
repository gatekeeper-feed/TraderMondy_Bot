import os
import requests
import xml.etree.ElementTree as ET

# Expanded News Queries covering Crypto Security, Geopolitics, Energy & Equities
ENHANCED_NEWS_QUERIES = {
    "Crypto & Security": "Binance OR Bybit OR hack OR exploit OR crypto security OR ETF",
    "Geopolitics & War": "Strait of Hormuz OR Red Sea OR tanker OR war OR missile OR tariffs OR sanction",
    "Macro & Crude": "crude oil OR brent OR OPEC OR US CPI OR Federal Reserve OR inflation OR yields",
    "Indian Equities": "Nifty 50 OR Sensex OR Bank Nifty OR RBI OR FII DII"
}

# Free RSS Feeds for real-time security and macro tracking
FREE_RSS_SOURCES = [
    {"url": "https://cointelegraph.com/rss", "source": "CoinTelegraph"},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "CoinDesk"},
    {"url": "https://decrypt.co/feed", "source": "Decrypt Media"}
]

def fetch_all_news():
    """
    Aggregates headlines from both NewsAPI queries and direct Crypto/Macro RSS feeds,
    ensuring zero blind spots for exchange hacks, war shocks, or tariff announcements.
    """
    headlines = []
    seen = set()

    # 1. Fetch from NewsAPI Queries
    news_api_key = os.getenv("NEWS_API_KEY")
    if news_api_key:
        for label, query in ENHANCED_NEWS_QUERIES.items():
            url = f"https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&pageSize=5&apiKey={news_api_key}"
            try:
                res = requests.get(url, timeout=8)
                if res.status_code == 200:
                    for art in res.json().get("articles", []):
                        title = art.get("title")
                        if title and title not in seen:
                            seen.add(title)
                            headlines.append(title)
            except Exception as e:
                print(f"NewsAPI error for {label}: {e}")

    # 2. Fetch from Free RSS Feeds (Instant Security / Exploit Tracking)
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

    return headlines[:12]  # Returns top unique multi-asset headlines
