import os
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

# ---------- Secrets (set in GitHub) ----------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# ---------- Settings ----------
IST = timezone(timedelta(hours=5, minutes=30))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
STATE_FILE = "state.json"
RR_TP1 = 3
RR_TP2 = 5

SYMS = {
    "Nifty 50": "^NSEI", "Sensex": "^BSESN", "Bank Nifty": "^NSEBANK", "India VIX": "^INDIAVIX",
    "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI", "Nikkei 225": "^N225", "Hang Seng": "^HSI",
    "Crude WTI": "CL=F", "Brent": "BZ=F", "USD/INR": "INR=X", "Dollar Index": "DX-Y.NYB",
    "US 10Y yield": "^TNX", "Gold": "GC=F", "Bitcoin": "BTC-USD",
}

NEWS_QUERIES = {
    "India market": "Nifty Sensex stock market India",
    "Global macro": "Fed OR RBI OR inflation OR crude oil OR dollar markets",
    "Gold": "gold price",
    "Bitcoin": "bitcoin crypto",
}


# ---------- Small helpers ----------
def now_ist():
    return datetime.now(IST)


def stamp():
    return now_ist().strftime("%d %b, %I:%M %p IST")


def fmt(x):
    return f"{x:,.2f}"


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def split_text(text, limit=3800):
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for part in split_text(text):
        try:
            r = requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": part, "disable_web_page_preview": True},
                timeout=30,
            )
            if not r.ok:
                print("Telegram error:", r.text[:300])
                return False
        except Exception as e:
            print("Telegram send failed:", type(e).__name__)
            return False
    return True


GEM = {"err": ""}


def ask_gemini(prompt):
    if not GEMINI_KEY:
        GEM["err"] = "no API key"
        return None
    attempts = [
        ("gemini-2.5-flash", True),
        ("gemini-2.5-flash", False),
        ("gemini-2.5-flash-lite", True),
        ("gemini-flash-latest", False),
    ]
    for model, quick in attempts:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 6000},
        }
        if quick:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        try:
            r = requests.post(url, headers={"x-goog-api-key": GEMINI_KEY}, json=body, timeout=60)
            data = r.json()
            cands = data.get("candidates")
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return re.sub(r"[*_`#]", "", text).strip()
                GEM["err"] = f"{model}: empty answer ({cands[0].get('finishReason')})"
            else:
                err = data.get("error", {})
                GEM["err"] = f"{model}: HTTP {r.status_code} {err.get('message') or data.get('promptFeedback') or ''}"
        except Exception as e:
            GEM["err"] = f"{model}: {type(e).__name__}"
        GEM["err"] = GEM["err"][:200]
        print("Gemini failed ->", GEM["err"])
        time.sleep(3)
    return None


# ---------- Market data ----------
def yahoo(symbol, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    for _ in range(3):
        try:
            r = requests.get(url, params={"interval": interval, "range": rng}, headers=HEADERS, timeout=20)
            res = r.json()["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            out = []
            for i, t in enumerate(ts):
                o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                if None in (o, h, l, c):
                    continue
                out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
            if out:
                return out
        except Exception as e:
            print(f"Yahoo {symbol} failed:", type(e).__name__)
        time.sleep(2)
    return []


def kraken(minutes):
    try:
        r = requests.get(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": "XBTUSD", "interval": minutes},
            timeout=20,
        )
        d = r.json()["result"]
        key = [k for k in d if k != "last"][0]
        return [
            {"t": int(x[0]), "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
            for x in d[key]
        ]
    except Exception as e:
        print("Kraken failed:", type(e).__name__)
        return []


def get_candles(asset, tf):
    """Returns CLOSED candles only (the unfinished last candle is dropped)."""
    if asset == "BTC":
        c = kraken(15 if tf == "15m" else 60)
        if not c:
            c = yahoo("BTC-USD", "15m" if tf == "15m" else "60m", "5d" if tf == "15m" else "1mo")
    else:
        c = yahoo("GC=F", "15m" if tf == "15m" else "60m", "5d" if tf == "15m" else "1mo")
    return c[:-1] if len(c) > 1 else c


def news(query, n=6):
    try:
        r = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query + " when:1d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
            headers=HEADERS,
            timeout=20,
        )
        root = ET.fromstring(r.content)
        items = []
        for it in root.iter("item"):
            title = it.findtext("title")
            if title:
                items.append(title)
            if len(items) >= n:
                break
        return items
    except Exception as e:
        print("News failed:", type(e).__name__)
        return []
