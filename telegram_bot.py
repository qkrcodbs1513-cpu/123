import requests

BOT_TOKEN = "8809590392:AAEbVr8nhDHjnmThBZ0Lcm3tETlk1LADTMc"
CHAT_ID = "8619378022"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ 텔레그램 전송 오류: {e}")
        return False