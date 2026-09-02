"""
Gold News Bot
=============
ดึงตารางข่าวเศรษฐกิจ (impact สูง, USD) + ข่าวที่เกี่ยวกับทองคำ แล้วส่งสรุปเข้า Telegram
พร้อมคำอธิบายสั้นๆ ว่าทำไมข่าวแต่ละประเภทถึงกระทบราคาทองคำ (กฎความสัมพันธ์เศรษฐศาสตร์พื้นฐาน
ไม่ใช้ AI ช่วยสรุป — ฟรี 100%)

Environment variables ที่ต้องตั้งค่า:
  FINNHUB_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import os
from datetime import datetime, timedelta, timezone

import requests

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# (keywords ที่ต้องเจออย่างน้อย 1 คำ, ป้ายกำกับหมวด, คำอธิบายว่าทำไมสำคัญกับทองคำ)
# เช็คตามลำดับ อันแรกที่ match ก่อนจะถูกใช้
CATEGORY_RULES = [
    (["fomc", "fed", "interest rate", "rate cut", "rate hike"],
     "🏦 ดอกเบี้ย / ท่าที Fed",
     "ลดดอกเบี้ย/ท่าทีผ่อนคลาย → ดอลลาร์อ่อน มักหนุนทองขึ้น | ขึ้นดอกเบี้ย/ท่าทีเข้มงวด → มักกดดันทองลง"),
    (["cpi", "ppi", "inflation"],
     "📈 เงินเฟ้อ",
     "เงินเฟ้อสูงกว่าคาด → ตลาดกลัว Fed คงดอกเบี้ยสูงต่อ กดดันทอง | ต่ำกว่าคาด → มักหนุนทองขึ้น"),
    (["nonfarm", "payroll", "jobless"],
     "👷 ตลาดแรงงานสหรัฐฯ",
     "จ้างงานแข็งแกร่ง → เศรษฐกิจแข็งแรง มักกดดันทอง | จ้างงานอ่อนแอ → มักหนุนทองขึ้น"),
    (["treasury yield"],
     "💵 ผลตอบแทนพันธบัตรสหรัฐฯ",
     "ผลตอบแทนพันธบัตรขึ้น → แย่งความน่าสนใจจากทอง (ทองไม่มีดอกเบี้ย) มักกดดันทอง | ลง → มักหนุนทอง"),
    (["dollar"],
     "💲 ค่าเงินดอลลาร์",
     "ทองคำเทรดเป็นดอลลาร์ ดอลลาร์แข็ง → ทองมักอ่อนตัว | ดอลลาร์อ่อน → ทองมักแข็งตัว"),
    (["geopolit", "recession", "safe haven"],
     "🛡️ ความเสี่ยง / สินทรัพย์ปลอดภัย",
     "ความไม่แน่นอนทางเศรษฐกิจ-การเมืองสูง → เงินมักไหลเข้าทองคำในฐานะสินทรัพย์ปลอดภัย"),
]
DEFAULT_LABEL = "🟡 ข่าวทองคำโดยตรง"
DEFAULT_EXPLANATION = "ข่าวที่พูดถึงทองคำ/XAU โดยตรง ควรติดตามปฏิกิริยาราคาต่อ"

KEYWORDS = [kw for rule in CATEGORY_RULES for kw in rule[0]] + ["gold", "xau"]


def categorize(headline_lower):
    for kws, label, explanation in CATEGORY_RULES:
        if any(kw in headline_lower for kw in kws):
            return label, explanation
    return DEFAULT_LABEL, DEFAULT_EXPLANATION


def get_economic_calendar():
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
        lines.append("")
        for n in news:
            headline = n.get("headline", "")
            src = n.get("source", "")
            label, explanation = categorize(headline.lower())
            lines.append(f"{label}")
            lines.append(f"• {headline}")
            lines.append(f"  (ที่มา: {src})")
            lines.append(f"  💡 ทำไมสำคัญ: {explanation}")
            lines.append("")
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
