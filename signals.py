from helpers import *


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
