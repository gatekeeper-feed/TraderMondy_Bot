import os
import sys
from datetime import datetime
from helpers import *
from signals import run_signals
from news_engine import fetch_all_news, fetch_breaking


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
    if ok < 5:
        send_telegram(
            f"⚠️ TRADER MONDY: {kind.upper()} report skipped. Market data sources are not responding right now. No numbers were made up."
        )
        save_state(state)
        return

    # --- ENHANCED NEWS INTEGRATION ---
    all_headlines = fetch_all_news()
    if all_headlines:
        news_text = "\n".join(f"- {t}" for t in all_headlines)
    else:
        heads = []
        for label, q in NEWS_QUERIES.items():
            items = news(q)
            if items:
                heads.append(f"[{label}]\n" + "\n".join(f"- {t}" for t in items))
        news_text = "\n\n".join(heads) if heads else "No headlines available."
    # ---------------------------------

    if kind == "premarket":
        title = "PRE-MARKET RADAR"
        sections = (
            "1) MARKET BIAS for today: Nifty 50, Sensex, Bank Nifty. For each: Bullish / Bearish / Neutral, a one-line reason, confidence (Low/Medium/High).\n"
            "2) KEY LEVELS: copy the provided levels for each index.\n"
            "3) GLOBAL AND MACRO IMPACT: US, Asia, crude, USD/INR, dollar index, US yields, India VIX.\n"
            "4) NEWS IMPACT: the 3 or 4 headlines that matter most and what each means for the assets.\n"
            "5) BUCKET IMPACT: Nifty, Sensex, Gold, Bitcoin: Bullish / Bearish / Neutral with a short reason.\n"
            "6) GAME PLAN: one line. Remind: option stop loss is 10 points (Nifty) and 20 points (Sensex) on the option premium, minimum 1:3 risk-reward."
        )
    else:
        title = "POST-MARKET WRAP"
        sections = (
            "1) HOW THE DAY CLOSED: Nifty 50, Sensex, Bank Nifty and India VIX.\n"
            "2) WHAT DROVE IT: use the data and headlines.\n"
            "3) OUTLOOK FOR TOMORROW: bias for Nifty, Sensex, Bank Nifty (Bullish / Bearish / Neutral, reason, confidence) with the provided levels.\n"
            "4) NEWS IMPACT: the 3 or 4 headlines that matter most and what each means for the assets.\n"
            "5) BUCKET IMPACT: Nifty, Sensex, Gold, Bitcoin: Bullish / Bearish / Neutral with a short reason.\n"
            "6) WATCH LIST for tomorrow: one line."
        )

    prompt = (
        f"You are the market analyst for the Telegram channel Trader Mondy. Write the {title} for Indian markets.\n"
        f"Current time: {stamp()}.\n"
        "STRICT RULES: use ONLY the data below. Never invent numbers. Gift Nifty, open interest, PCR and option Greeks are NOT provided, so do not mention values for them. "
        "Plain text only: no markdown symbols (* _ # `), short lines, a few emojis are fine. Keep it under 2500 characters.\n\n"
        f"SECTIONS:\n{sections}\n\n"
        "MARKET DATA (last close / latest and % change):\n" + "\n".join(rows) + "\n\n"
        "LEVELS:\n" + "\n".join(pivots) + "\n\n"
        f"HEADLINES (last 24h):\n{news_text}\n\n"
        "End with: Educational only, not investment advice."
    )

    ai = ask_gemini(prompt)
    header = f"📈 TRADER MONDY: {title}\n🕒 {stamp()}\n──────────────────────────────────\n"
    if ai:
        body = ai
    else:
        body = f"⚠️ AI analysis unavailable right now ({GEM['err']}). Raw data:\n\n" + "\n".join(rows) + "\n\n" + "\n".join(pivots)
    if send_telegram(header + body):
        state["last_" + kind] = now_ist().strftime("%Y-%m-%d")
        print(f"{kind} report sent")
    save_state(state)


# ---------- Breaking news watch ----------
def build_news_prompt(headline):
    return (
        "You are the market analyst for the Telegram channel Trader Mondy. A news headline just broke.\n"
        f"HEADLINE: {headline}\n"
        f"Current time: {stamp()}.\n"
        "The channel follows Bitcoin, Ethereum, Gold, Silver, Nifty 50, Sensex and Bank Nifty.\n"
        "RULES: use only the headline and well-known market logic. Never invent numbers, prices or facts that are not in the headline. "
        "Plain text only: no markdown symbols (* _ # `), no links. Maximum 900 characters. Be specific, not generic.\n"
        "Write exactly this layout:\n"
        "⚡ DIRECT IMPACT: one or two lines on what this hits first and why it matters.\n"
        "📊 DIRECTION:\n"
        "Bitcoin: Bullish/Bearish/Neutral - short reason\n"
        "Ethereum: Bullish/Bearish/Neutral - short reason\n"
        "Gold: Bullish/Bearish/Neutral - short reason\n"
        "Silver: Bullish/Bearish/Neutral - short reason\n"
        "Nifty and Sensex: Bullish/Bearish/Neutral - short reason\n"
        "Bank Nifty: Bullish/Bearish/Neutral - short reason\n"
        "🔗 KNOCK-ON EFFECTS: two or three short lines on the chain reaction into the related markets.\n"
        "⏳ TIMEFRAME: Intraday, 1-2 days or Longer, plus the one level or event to watch."
    )


def run_news_watch():
    state = load_state()
    first_run = "seen_news" not in state
    seen = list(state.get("seen_news", []))
    now = now_ist()

    # remember which topics were alerted in the last 6 hours (stops repeat alerts on the same story)
    topics = {}
    for k, v in state.get("seen_topics", {}).items():
        try:
            if (now - datetime.fromisoformat(v)).total_seconds() < 6 * 3600:
                topics[k] = v
        except Exception:
            pass

    fresh = [i for i in fetch_breaking() if i["id"] not in seen]
    if first_run:
        seen += [i["id"] for i in fresh]
        print(f"First run: remembered {len(fresh)} headlines, no alerts sent")
    else:
        sent = 0
        for i in fresh:
            topic = i.get("topic")
            if topic and topic in topics:
                seen.append(i["id"])
                continue
            if sent >= 3:
                break
            view = ask_gemini(build_news_prompt(i["title"]))
            msg = f"🚨 BREAKING NEWS\n🕒 {stamp()}\n\n📰 {i['title']}\n\n"
            if view:
                msg += view.strip()
            else:
                msg += "AI impact view is unavailable right now. Treat this headline with caution."
            msg += "\n\nEducational only, not investment advice."
            if send_telegram(msg):
                seen.append(i["id"])
                sent += 1
                if topic:
                    topics[topic] = now.isoformat()

    state["seen_news"] = seen[-400:]
    state["seen_topics"] = topics
    save_state(state)


# ---------- Test mode ----------
def run_test():
    lines = ["✅ Trader Mondy bot is connected.", f"🕒 {stamp()}", ""]
    for asset in ["BTC", "GOLD"]:
        c = get_candles(asset, "15m")
        lines.append(f"{asset} data: OK (last {fmt(c[-1]['c'])})" if c else f"{asset} data: FAILED")
    n = yahoo("^NSEI", "1d", "5d")
    lines.append(f"Nifty data: OK (last {fmt(n[-1]['c'])})" if n else "Nifty data: FAILED")

    enhanced_news = fetch_all_news()
    if enhanced_news:
        lines.append(f"News Engine: OK ({len(enhanced_news)} headlines fetched)")
    else:
        lines.append(f"News: OK ({len(news('Nifty Sensex'))} fallback headlines)" if news("Nifty Sensex") else "News: FAILED")

    breaking = fetch_breaking()
    lines.append(f"Breaking-news watch: OK ({len(breaking)} matching headlines right now)")

    g = ask_gemini("Reply with the single word OK.")
    lines.append("Gemini AI: OK" if g else "Gemini AI: FAILED (check the API key)")
    send_telegram("\n".join(lines))
    save_state(load_state())


def decide_mode():
    ev = os.getenv("EVENT_NAME", "")
    sch = os.getenv("SCHEDULE", "")
    inp = os.getenv("INPUT_MODE", "")
    if ev == "workflow_dispatch":
        return inp or "test"
    if sch == "30 2 * * 1-5":
        return "premarket"
    if sch == "30 10 * * 1-5":
        return "postmarket"
    if sch == "2-59/5 * * * *":
        return "news"
    return "signals"


if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID secret")
        sys.exit(1)
    mode = decide_mode()
    print("Mode:", mode)
    if mode == "signals":
        run_signals()
    elif mode == "news":
        run_news_watch()
    elif mode in ("premarket", "postmarket"):
        run_report(mode)
    else:
        run_test()
