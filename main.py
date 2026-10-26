import os
import requests
import google.genai as genai

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
    
    # Initialize Gemini AI Client
    client = genai.Client(api_key=GEMINI_KEY)
    
    prompt = """
    You are the automated Trading Intelligence Engine for Trader Mondy (@tradermondy).
    Generate a formatted Pre-Market Radar & Confirmation Analysis for today based on Trading strategy Mondy.
    Include macro cues (Gift Nifty, VIX, Crude Oil, USD/INR), direction bias for Nifty 50 and Sensex, and strict option SL rules (10 pts Nifty / 20 pts Sensex).
    Keep it concise, structured, and ready for Telegram Markdown.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    alert_text = f"📈 *TRADER MONDY: PRE-MARKET RADAR*\n──────────────────────────────────\n{response.text}"
    send_telegram_alert(alert_text)
    print("Pre-market radar alert sent successfully to Telegram!")

if __name__ == "__main__":
    process_trading_strategy_mondy()
