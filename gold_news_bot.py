"""
Gold News Bot
=============
ดึงตารางข่าวเศรษฐกิจ (impact สูง, USD) + ข่าวที่เกี่ยวกับทองคำ แล้วส่งสรุปเข้า Telegram
ใช้ข้อมูลจาก Finnhub (ฟรี, ถูกกฎหมาย ไม่ใช่การ scrape) — สมัครคีย์ฟรีได้ที่ https://finnhub.io

Environment variables ที่ต้องตั้งค่า:
  FINNHUB_API_KEY     - API key จาก finnhub.io
  TELEGRAM_BOT_TOKEN  - token จาก @BotFather
  TELEGRAM_CHAT_ID    - chat id ของคุณ (ดูวิธีหาใน setup guide)
"""

import os
from datetime import datetime, timedelta, timezone

import requests

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# คำที่ใช้กรองข่าวว่าเกี่ยวกับทองคำ/ปัจจัยที่กระทบทองคำหรือไม่
KEYWORDS = [
    "gold", "xau", "fed", "fomc", "dollar", "inflation", "cpi", "ppi",
    "interest rate", "rate cut", "rate hike", "nonfarm", "payroll",
    "jobless", "treasury yield", "recession", "geopolit", "safe haven",
]


def get_economic_calendar():
    """ตารางข่าวเศรษฐกิจวันนี้-พรุ่งนี้ กรองเฉพาะ USD + impact สูง (ตัวขับเคลื่อนหลักของราคาทอง)"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/calendar/economic"
    params = {"from": today, "to": tomorrow, "token": FINNHUB_API_KEY}

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json().get("economicCalendar", [])

    def is_high_impact_usd(e):
        impact = str(e.get("impact", "")).lower()
        return e.get("country") == "US" and impact in ("3", "high")

    return [e for e in data if is_high_impact_usd(e)]


def get_gold_related_news():
    """ข่าวการเงินล่าสุด กรองเฉพาะที่เกี่ยวกับทองคำ/ปัจจัยที่กระทบทองคำ (สูงสุด 5 ข่าว)"""
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": FINNHUB_API_KEY}

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    news = r.json()

    matched = []
    for n in news:
        headline = (n.get("headline") or "").lower()
        if any(kw in headline for kw in KEYWORDS):
            matched.append(n)
        if len(matched) >= 5:
            break
    return matched


def format_message(events, news):
    now_th = datetime.now(timezone.utc) + timedelta(hours=7)
    lines = [f"🟡 สรุปปัจจัยทองคำวันนี้ ({now_th.strftime('%d/%m/%Y')})", ""]

    if events:
        lines.append("📅 ข่าวเศรษฐกิจ USD (impact สูง):")
        for e in events:
            t = e.get("time", "")
            ev = e.get("event", "")
            actual = e.get("actual")
            forecast = e.get("estimate")
            prev = e.get("prev")

            line = f"• {t} | {ev}"
            extra = []
            if forecast is not None:
                extra.append(f"คาด {forecast}")
            if prev is not None:
                extra.append(f"ก่อนหน้า {prev}")
            if extra:
                line += f" ({', '.join(extra)})"
            if actual is not None:
                line += f" → จริง {actual}"
            lines.append(line)
        lines.append("")
    else:
        lines.append("📅 วันนี้ไม่มีข่าวเศรษฐกิจ impact สูงของ USD")
        lines.append("")

    if news:
        lines.append("📰 ข่าวที่เกี่ยวข้องกับทองคำ:")
        for n in news:
            headline = n.get("headline", "")
            src = n.get("source", "")
            link = n.get("url", "")
            lines.append(f"• {headline} ({src})\n  {link}")
        lines.append("")
    else:
        lines.append("📰 ยังไม่มีข่าวด่วนเกี่ยวกับทองคำในตอนนี้")
        lines.append("")

    lines.append("⚠️ สรุปข้อมูลเพื่อประกอบการวิเคราะห์ ไม่ใช่คำแนะนำการลงทุน")
    return "\n".join(lines)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram จำกัดความยาวข้อความ ~4096 ตัวอักษร ตัดส่งเป็นท่อนถ้ายาวเกิน
    for i in range(0, len(message), 3500):
        chunk = message[i:i + 3500]
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk})
        r.raise_for_status()


def main():
    events = get_economic_calendar()
    news = get_gold_related_news()
    message = format_message(events, news)
    send_telegram(message)
    print("ส่งสำเร็จ:\n")
    print(message)


if __name__ == "__main__":
    main()
