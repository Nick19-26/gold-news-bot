"""
Gold Breaking News Alert
=========================
รันถี่ (ทุก 5 นาที ตาม workflow) เช็คข่าวใหม่ที่เกี่ยวกับทองคำจาก Finnhub
ส่งเฉพาะข่าว "ใหม่" ที่ยังไม่เคยส่งเข้า Telegram ทันที (กันส่งซ้ำด้วยไฟล์ sent_ids.json)
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
LOOKBACK_MINUTES = 60  # กันข่าวเก่าถูกส่งรัวๆ ตอนรันครั้งแรก

KEYWORDS = [
    "gold", "xau", "fed", "fomc", "dollar", "inflation", "cpi", "ppi",
    "interest rate", "rate cut", "rate hike", "nonfarm", "payroll",
    "jobless", "treasury yield", "recession", "geopolit", "safe haven",
]


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
        return

    for n in reversed(new_items):
        headline = n.get("headline", "")
        src = n.get("source", "")
        link = n.get("url", "")
        text = f"🚨 ข่าวด่วนทองคำ\n{headline} ({src})\n{link}"
        send_telegram(text)
        sent_ids.add(n.get("id"))

    save_sent_ids(sent_ids)
    print(f"ส่งข่าวใหม่ {len(new_items)} ข่าว")


if __name__ == "__main__":
    main()
