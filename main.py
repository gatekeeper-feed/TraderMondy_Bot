import os
import time
import requests

# Fetch Secrets
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "📌 Hold Position", "callback_data": "hold"},
                    {"text": "❌ Square Off", "callback_data": "exit"},
                    {"text": "➕ Add Lot", "callback_data": "add"}
                ]
            ]
        }
    }
    response = requests.post(url, json=payload)
    return response.json()

def process_trading_strategy_mondy():
    print("Initializing Trading strategy Mondy Engine...")
    
    prompt = """
    You are the automated Trading Intelligence Engine for Trader Mondy (@tradermondy).
    Generate a formatted Pre-Market Radar & Confirmation Analysis for today based on Trading strategy Mondy.
    Include macro cues (Gift Nifty, VIX, Crude Oil, USD/INR), direction bias for Nifty 50 and Sensex, and strict option SL rules (10 pts Nifty / 20 pts Sensex).
    Keep it concise, structured, and ready for Telegram Markdown.
    """
    
    # Corrected endpoint using gemini-3.8-flash
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    max_retries = 3
    ai_content = None
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Calling Gemini API (Attempt {attempt}/{max_retries})...")
            response = requests.post(api_url, json=payload, timeout=30)
            data = response.json()
            
            if "candidates" in data:
                ai_content = data["candidates"][0]["content"]["parts"][0]["text"]
                break
            else:
                print(f"API Response Error: {data}")
                if attempt == max_retries:
                    raise Exception(f"Gemini API Error: {data}")
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise e
            time.sleep(5)

    alert_text = f"📈 *TRADER MONDY: PRE-MARKET RADAR*\n──────────────────────────────────\n{ai_content}"
    send_telegram_alert(alert_text)
    print("Pre-market radar alert sent successfully to Telegram!")

if __name__ == "__main__":
    process_trading_strategy_mondy()
