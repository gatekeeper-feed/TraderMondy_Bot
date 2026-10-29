if ok < 5:
        send_telegram(f"⚠️ TRADER MONDY: {kind.upper()} report skipped. Market data sources are not responding right now. No numbers were made up.")
        save_state(state)
        return

    heads = []
    for label, q in NEWS_QUERIES.items():
        items = news(q)
        if items:
            heads.append(f"[{label}]\n" + "\n".join(f"- {t}" for t in items))
    news_text = "\n\n".join(heads) if heads else "No headlines available."

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
        body = f"⚠️ AI analysis unavailable right now ({LAST_GEMINI_ERROR}). Raw data:\n\n" + "\n".join(rows) + "\n\n" + "\n".join(pivots)
    if send_telegram(header + body):
        state["last_" + kind] = now_ist().strftime("%Y-%m-%d")
        print(f"{kind} report sent")
    save_state(state)


# ---------- Test mode ----------
def run_test():
    lines = ["✅ Trader Mondy bot is connected.", f"🕒 {stamp()}", ""]
    for asset in ["BTC", "GOLD"]:
        c = get_candles(asset, "15m")
        lines.append(f"{asset} data: OK (last {fmt(c[-1]['c'])})" if c else f"{asset} data: FAILED")
    n = yahoo("^NSEI", "1d", "5d")
    lines.append(f"Nifty data: OK (last {fmt(n[-1]['c'])})" if n else "Nifty data: FAILED")
    lines.append(f"News: OK ({len(news('Nifty Sensex'))} headlines)" if news("Nifty Sensex") else "News: FAILED")
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
    return "signals"


if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID secret")
        sys.exit(1)
    mode = decide_mode()
    print("Mode:", mode)
    if mode == "signals":
        run_signals()
    elif mode in ("premarket", "postmarket"):
        run_report(mode)
    else:
        run_test()
