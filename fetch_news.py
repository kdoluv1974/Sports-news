#!/usr/bin/env python3
"""يقرأ خلاصات RSS من sources.json، يحذف المكرر، يترجم العناوين غير العربية،
ثم يكتب docs/news.json الذي تعرضه صفحة index.html."""
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from deep_translator import GoogleTranslator

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "news.json"
MAX_AGE = timedelta(days=3)   # أقدم خبر يُحتفظ به
MAX_ITEMS = 300
SUMMARY_LEN = 200

# ترتيب الفحص مهم: الرياضات المحددة أولاً ثم كرة القدم
SPORTS = [
    ("كرة السلة", ["nba", "basketball", "euroleague", "كرة السلة", "السلة"]),
    ("التنس", ["tennis", "wimbledon", "atp", "wta", "grand slam", "التنس"]),
    ("سباقات", ["formula 1", "formula one", "f1", "grand prix", "motogp", "فورمولا", "موتو جي بي"]),
    ("القتال", ["ufc", "mma", "boxing", "ملاكمة", "فنون قتالية"]),
    ("كرة القدم", ["football", "soccer", "premier league", "champions league", "la liga",
                    "serie a", "bundesliga", "fifa", "uefa", "كرة القدم", "الدوري", "دوري أبطال", "المنتخب"]),
]
OTHER = "رياضات أخرى"

translator = GoogleTranslator(source="auto", target="ar")


def classify(text: str) -> str:
    low = text.lower()
    for sport, words in SPORTS:
        for w in words:
            if w.isascii():
                if re.search(r"\b" + re.escape(w) + r"\b", low):
                    return sport
            elif w in low:
                return sport
    return OTHER


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def translate(text: str):
    if not text:
        return ""
    for attempt in range(3):
        try:
            return translator.translate(text) or None
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None  # يُعاد المحاولة في التشغيل القادم


def find_image(entry) -> str:
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    m = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", "") or "")
    return m.group(1) if m else ""


def published(entry) -> datetime:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def norm(title: str) -> str:
    return re.sub(r"[\W_]+", "", title.lower())


def load_previous() -> dict:
    try:
        data = json.loads(OUT.read_text("utf-8"))
        return {i["link"]: i for i in data["items"]}
    except Exception:
        return {}


def main():
    sources = json.loads((ROOT / "sources.json").read_text("utf-8"))
    previous = load_previous()
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    items, seen_links, seen_titles = [], set(), set()

    for src in sources:
        feed = feedparser.parse(src["url"])
        if not feed.entries:
            print(f"تحذير: لا أخبار من {src['name']} ({src['url']})")
            continue
        for e in feed.entries:
            link, title = e.get("link"), clean(e.get("title"))
            if not link or not title:
                continue
            source_name = src["name"]
            if src.get("gnews"):  # عناوين أخبار Google تنتهي بـ " - اسم الموقع"
                title = re.sub(r"\s+-\s+[^-]+$", "", title)
            when = published(e)
            if when < cutoff or link in seen_links or norm(title) in seen_titles:
                continue
            seen_links.add(link)
            seen_titles.add(norm(title))

            summary = clean(e.get("summary"))[:SUMMARY_LEN]
            sport = src["sport"]
            if sport == "general":
                sport = classify(title + " " + summary)

            item = {
                "title": title,
                "summary": summary,
                "link": link,
                "image": find_image(e),
                "source": source_name,
                "lang": src["lang"],
                "sport": sport,
                "published": when.isoformat(),
            }
            old = previous.get(link)
            if src["lang"] == "ar":
                item["title_ar"], item["summary_ar"] = title, summary
            elif old and old.get("title_ar"):
                item["title_ar"], item["summary_ar"] = old["title_ar"], old.get("summary_ar", "")
            else:
                item["title_ar"] = translate(title)
                item["summary_ar"] = translate(summary) if item["title_ar"] else None
            items.append(item)

    if not items:
        print("لم يُجمع أي خبر؛ تُترك news.json القديمة كما هي.")
        return

    items.sort(key=lambda i: i["published"], reverse=True)
    items = items[:MAX_ITEMS]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "items": items},
                   ensure_ascii=False, indent=1),
        "utf-8",
    )
    print(f"تم: {len(items)} خبر")


if __name__ == "__main__":
    main()
