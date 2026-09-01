"""
Gold News Bot
=============
ดึงตารางข่าวเศรษฐกิจ (impact สูง, USD) + ข่าวที่เกี่ยวกับทองคำ แล้วส่งสรุปเข้า Telegram
ใช้ข้อมูลจาก Finnhub (ฟรี, ถูกกฎหมาย ไม่ใช่การ scrape) — สมัครคีย์ฟรีได้ที่ https://finnhub.io

ออกแบบให้ทนต่อ error: ถ้าแหล่งข้อมูลไหนดึงไม่ได้ (เช่น endpoint กลายเป็น premium-only)
จะข้ามส่วนนั้นแล้วส่งสรุปเท่าที่ดึงได้ ไม่ทำให้ทั้งระบบพัง

Environment variables ที่ต้องตั้งค่า:
  FINNHUB_API_KEY     - API key จาก finnhub.io
  TELEGRAM_BOT_TOKEN  - token จาก @BotFather
  TELEGRAM_CHAT_ID    - chat id ของคุณ
"""

import os
from datetime import datetime, timedelta, timezone

import requests

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = [
    "gold", "xau", "fed", "fomc", "dollar", "inflation", "cpi", "ppi",
    "interest rate", "rate cut", "rate hike", "nonfarm", "payroll",
    "jobless", "treasury yield", "recession", "geopolit", "safe haven",
]


def get_economic_calendar():
    """ตารางข่าวเศรษฐกิจวันนี้-พรุ่งนี้ กรองเฉพาะ USD + impact สูง
    หมายเหตุ: endpoint นี้บาง account อาจต้องเป็น premium ของ Finnhub —
    ถ้าเจอ error จะคืนค่า None (ไม่ใช่ list ว่าง) เพื่อแยกแยะว่า 'ดึงไม่ได้' กับ 'วันนี้ไม่มีข่าว'
    """
    try:
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
    except Exception as exc:
        print(f"[warn] ดึงตารางข่าวเศรษฐกิจไม่ได้: {exc}")
        return None


def get_gold_related_news():
    """ข่าวการเงินล่าสุด กรองเฉพาะที่เกี่ยวกับทองคำ (สูงสุด 5 ข่าว)
    คืนค่า None ถ้าดึงไม่ได้เลย, คืนค่า [] ถ้าดึงได้แต่ไม่มีข่าวที่ตรง keyword
    """
    try:
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
    except Exception as exc:
        print(f"[warn] ดึงข่าวทองคำไม่ได้: {exc}")
        return None


def format_message(events, news):
    now_th = datetime.now(timezone.utc) + timedelta(hours=7)
    lines = [f"🟡 สรุปปัจจัยทองคำวันนี้ ({now_th.strftime('%d/%m/%Y')})", ""]

    if events is None:
        lines.append("📅 (ดึงตารางข่าวเศรษฐกิจไม่ได้รอบนี้)")
        lines.append("")
    elif events:
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

    if news is None:
        lines.append("📰 (ดึงข่าวทองคำไม่ได้รอบนี้)")
    elif news:
        lines.append("📰 ข่าวที่เกี่ยวข้องกับทองคำ:")
        for n in news:
            headline = n.get("headline", "")
            src = n.get("source", "")
            link = n.get("url", "")
            lines.append(f"• {headline} ({src})\n  {link}")
    else:
        lines.append("📰 ยังไม่มีข่าวด่วนเกี่ยวกับทองคำในตอนนี้")

    lines.append("")
    lines.append("⚠️ สรุปข้อมูลเพื่อประกอบการวิเคราะห์ ไม่ใช่คำแนะนำการลงทุน")
    return "\n".join(lines)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
