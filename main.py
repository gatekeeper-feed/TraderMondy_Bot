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


LAST_GEMINI_ERROR = ""


def ask_gemini(prompt):
    global LAST_GEMINI_ERROR
    if not GEMINI_KEY:
        LAST_GEMINI_ERROR = "no API key"
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
                LAST_GEMINI_ERROR = f"{model}: empty answer ({cands[0].get('finishReason')})"
            else:
                err = data.get("error", {})
                LAST_GEMINI_ERROR = f"{model}: HTTP {r.status_code} {err.get('message') or data.get('promptFeedback') or ''}"
        except Exception as e:
            LAST_GEMINI_ERROR = f"{model}: {type(e).__name__}"
        LAST_GEMINI_ERROR = LAST_GEMINI_ERROR[:200]
        print("Gemini failed ->", LAST_GEMINI_ERROR)
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


# ---------- Signal logic (Gold + BTC) ----------
def swings(c, k=3):
    highs, lows = [], []
    for i in range(k, len(c) - k):
        if all(c[i]["h"] > c[i - j]["h"] and c[i]["h"] >= c[i + j]["h"] for j in range(1, k + 1)):
            highs.append(i)
        if all(c[i]["l"] < c[i - j]["l"] and c[i]["l"] <= c[i + j]["l"] for j in range(1, k + 1)):
            lows.append(i)
    return highs, lows


def find_choch(c, highs, lows, look=20):
    n = len(c)
    for i in range(n - 1, n - look - 1, -1):
        ph = [x for x in highs if x < i]
        pl = [x for x in lows if x < i]
        if len(ph) < 2 or len(pl) < 2:
            continue
        h1, h2 = c[ph[-1]]["h"], c[ph[-2]]["h"]
        l1, l2 = c[pl[-1]]["l"], c[pl[-2]]["l"]
        if h1 < h2 and l1 < l2 and c[i]["c"] > h1 and c[i - 1]["c"] <= h1:
            return {"dir": "LONG", "idx": i, "level": h1, "sl_ref": l1}
        if h1 > h2 and l1 > l2 and c[i]["c"] < l1 and c[i - 1]["c"] >= l1:
            return {"dir": "SHORT", "idx": i, "level": l1, "sl_ref": h1}
    return None


def find_fvg_retest(c, choch):
    n = len(c)
    last = c[-1]
    for j in range(n - 2, max(2, choch["idx"] - 2), -1):
        if choch["dir"] == "LONG" and c[j]["l"] > c[j - 2]["h"]:
            lo, hi = c[j - 2]["h"], c[j]["l"]
            if last["l"] <= hi and last["c"] >= lo:
                return (lo, hi)
        if choch["dir"] == "SHORT" and c[j]["h"] < c[j - 2]["l"]:
            lo, hi = c[j]["h"], c[j - 2]["l"]
            if last["h"] >= lo and last["c"] <= hi:
                return (lo, hi)
    return None


def find_order_blocks(h1):
    recent = h1[-120:]
    bodies = [abs(x["c"] - x["o"]) for x in recent[-50:]]
    avg_body = sum(bodies) / len(bodies) if bodies else 0
    bull, bear = [], []
    for i in range(1, len(recent) - 1):
        cur, nxt = recent[i], recent[i + 1]
        strong = abs(nxt["c"] - nxt["o"]) > 1.5 * avg_body
        if cur["c"] < cur["o"] and nxt["c"] > cur["h"] and strong:
            bull.append((cur["l"], cur["h"]))
        if cur["c"] > cur["o"] and nxt["c"] < cur["l"] and strong:
            bear.append((cur["l"], cur["h"]))
    return bull[-8:], bear[-8:]


def analyze(asset):
    c15 = get_candles(asset, "15m")
    h1 = get_candles(asset, "1h")
    if len(c15) < 60 or len(h1) < 30:
        print(f"{asset}: not enough data")
        return None
    if time.time() - c15[-1]["t"] > 5400:
        print(f"{asset}: market closed / data stale, skipping")
        return None

    highs, lows = swings(c15)
    choch = find_choch(c15, highs, lows)
    if not choch:
        print(f"{asset}: no CHoCH")
        return None
    fvg = find_fvg_retest(c15, choch)
    if not fvg:
        print(f"{asset}: CHoCH but no FVG retest")
        return None

    bull_ob, bear_ob = find_order_blocks(h1)
    zones = bull_ob if choch["dir"] == "LONG" else bear_ob
    window = c15[max(0, choch["idx"] - 10):]
    ob = None
    for lo, hi in zones:
        if any(x["l"] <= hi and x["h"] >= lo for x in window):
            ob = (lo, hi)
    if not ob:
        print(f"{asset}: no 1H order block confluence")
        return None

    atr = sum(x["h"] - x["l"] for x in c15[-14:]) / 14
    entry = c15[-1]["c"]
    if choch["dir"] == "LONG":
        sl = choch["sl_ref"] - 0.2 * atr
        risk = max(entry - sl, 0.5 * atr)
        sl = entry - risk
        tp1, tp2 = entry + RR_TP1 * risk, entry + RR_TP2 * risk
    else:
        sl = choch["sl_ref"] + 0.2 * atr
        risk = max(sl - entry, 0.5 * atr)
        sl = entry + risk
        tp1, tp2 = entry - RR_TP1 * risk, entry - RR_TP2 * risk
    if risk <= 0 or risk / entry > 0.03:
        print(f"{asset}: stop too wide, skipping")
        return None

    return {
        "asset": asset, "dir": choch["dir"], "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
        "choch_level": choch["level"], "choch_t": c15[choch["idx"]]["t"], "fvg": fvg, "ob": ob,
    }


def run_signals():
    state = load_state()
    names = {"BTC": "BITCOIN (BTC/USD)", "GOLD": "GOLD (futures)"}
    for asset in ["BTC", "GOLD"]:
        try:
            sig = analyze(asset)
        except Exception as e:
            print(f"{asset} analysis error:", type(e).__name__, e)
            continue
        if not sig:
            continue
        key = f"{sig['dir']}|{sig['choch_t']}"
        if state.get("last_signal", {}).get(asset) == key:
            print(f"{asset}: signal already sent")
            continue

        icon = "🟢" if sig["dir"] == "LONG" else "🔴"
        why = (
            f"CHoCH through {fmt(sig['choch_level'])}, FVG retest {fmt(sig['fvg'][0])}-{fmt(sig['fvg'][1])}, "
            f"1H order block {fmt(sig['ob'][0])}-{fmt(sig['ob'][1])}"
        )
        note = ask_gemini(
            f"In 2 short plain-text lines (no markdown), explain this {sig['dir']} setup on {names[asset]} "
            f"to a trader. Use only these facts: {why}. Entry {fmt(sig['entry'])}, stop {fmt(sig['sl'])}. "
            f"Do not add any other numbers or predictions."
        )
        msg = (
            f"{icon} {names[asset]}: {sig['dir']} SETUP\n"
            f"🕒 {stamp()}  (15m chart)\n"
            f"──────────────────────────────────\n"
            f"Entry: {fmt(sig['entry'])}\n"
            f"Stop loss: {fmt(sig['sl'])}\n"
            f"Target 1 (1:{RR_TP1}): {fmt(sig['tp1'])}\n"
            f"Target 2 (1:{RR_TP2}): {fmt(sig['tp2'])}\n\n"
            f"Why: {why}\n"
        )
        if note:
            msg += f"\n{note}\n"
        msg += "\n⚠️ Educational only, not investment advice. Alert may be delayed by a few minutes, so check the live price before acting."
        if send_telegram(msg):
            state.setdefault("last_signal", {})[asset] = key
            print(f"{asset}: signal sent")
    save_state(state)


# ---------- Indian market pre / post market reports ----------
def build_snapshot():
    rows, pivots = [], []
    for name, sym in SYMS.items():
        d = yahoo(sym, "1d", "10d")
        if len(d) < 2:
            rows.append(f"{name}: data unavailable")
            continue
        last, prev = d[-1], d[-2]
        chg = (last["c"] / prev["c"] - 1) * 100
        rows.append(f"{name}: {last['c']:,.2f} ({chg:+.2f}%)")
        if name in ("Nifty 50", "Sensex", "Bank Nifty"):
            h, l, c = last["h"], last["l"], last["c"]
            pp = (h + l + c) / 3
            day = datetime.fromtimestamp(last["t"], IST).strftime("%d %b")
            pivots.append(
                f"{name} levels from {day} session (High {h:,.0f}, Low {l:,.0f}, Close {c:,.0f}): "
                f"S2 {pp - (h - l):,.0f} | S1 {2 * pp - h:,.0f} | Pivot {pp:,.0f} | "
                f"R1 {2 * pp - l:,.0f} | R2 {pp + (h - l):,.0f}"
            )
    return rows, pivots


def run_report(kind):
    state = load_state()
    rows, pivots = build_snapshot()
    ok = sum(1 for r in rows if "unavailable" not in r)
    if ok
