"""
Gold Breaking News Alert
=========================
รันถี่ (ทุก 5 นาที ตาม workflow) เช็คข่าวใหม่ที่เกี่ยวกับทองคำจาก Finnhub
ส่งเฉพาะข่าว "ใหม่" ที่ยังไม่เคยส่ง พร้อมคำอธิบายว่าทำไมสำคัญกับทองคำ (ไม่ใช้ AI, ฟรี 100%)
กันส่งซ้ำด้วยไฟล์ sent_ids.json
"""

import json
import os
from datetime import datetime, timedelta, timezone

import requests

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "sent_ids.json"
MAX_STORED_IDS = 500
LOOKBACK_MINUTES = 60

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
     "ผลตอบแทนพันธบัตรขึ้น → แย่งความน่าสนใจจากทอง มักกดดันทอง | ลง → มักหนุนทอง"),
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


def load_sent_ids():
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent_ids(ids):
    trimmed = list(ids)[-MAX_STORED_IDS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f)


def get_fresh_news():
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": FINNHUB_API_KEY}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    r.raise_for_status()


def main():
    sent_ids = load_sent_ids()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

    try:
        news = get_fresh_news()
    except Exception as exc:
        print(f"[warn] ดึงข่าวไม่ได้รอบนี้: {exc}")
        save_sent_ids(sent_ids)
        return

    new_items = []
    for n in news:
        nid = n.get("id")
        if nid is None or nid in sent_ids:
            continue
        headline = (n.get("headline") or "").lower()
        if not any(kw in headline for kw in KEYWORDS):
            continue
        ts = n.get("datetime")
        if ts and datetime.fromtimestamp(ts, tz=timezone.utc) < cutoff:
            continue
        new_items.append(n)

    if not new_items:
        print("ไม่มีข่าวใหม่รอบนี้")
        save_sent_ids(sent_ids)
        return

    for n in reversed(new_items):
        headline = n.get("headline", "")
        src = n.get("source", "")
        label, explanation = categorize(headline.lower())
        text = (
            f"🚨 ข่าวด่วนทองคำ\n"
            f"{label}\n"
            f"{headline}\n"
            f"(ที่มา: {src})\n"
            f"💡 ทำไมสำคัญ: {explanation}"
        )
        send_telegram(text)
        sent_ids.add(n.get("id"))

    save_sent_ids(sent_ids)
    print(f"ส่งข่าวใหม่ {len(new_items)} ข่าว")


if __name__ == "__main__":
    main()
