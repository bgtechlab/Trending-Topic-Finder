"""
Trending Topic Finder — 5 Channels
====================================
Sirf Telegram Bot API + GitHub Actions se chalta hai. Koi paid/official
YouTube/Google/Reddit API key nahi chahiye — sab public endpoints /
yt-dlp scraping se kaam hota hai. (Gemini scoring optional hai, agar
GEMINI_API_KEY secret set hai to use hota hai, warna heuristic scoring
apne aap chal jaata hai.)

Features:
  - Multi-source trend detection: YouTube + Reddit + Google Trends
  - Duplicate topic filtering (history.json ke against)
  - Recency + view-count based smart sorting
  - Optional AI (Gemini) viral-potential scoring
  - Competitor channel watch
  - Telegram inline buttons: ✅ Use this / ❌ Skip (list track hoti hai)
  - Daily scheduled run + manual "/start" run dono support
  - Performance feedback loop (purani uploaded videos ke views check)

Auto-pipeline (topic -> video -> upload) is NOT included (user ne mana kiya).
"""

import os
import json
import time
import subprocess
import requests
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------
# CONFIG — 5 channels aur unki niche keywords
# ---------------------------------------------------------------------

CHANNELS = {
    "sg-news-automation": {
        "label": "SG News (Sarkari Result)",
        "keywords": ["sarkari result 2026", "government job news", "sarkari naukri"],
        "competitors": [],  # yahan competitor channel URLs daal sakte hain
    },
    "tech-review-bot": {
        "label": "TechGlow India",
        "keywords": ["new phone launch 2026", "gadget review india", "smartphone unboxing"],
        "competitors": [],
    },
    "bg-auto-job-bot": {
        "label": "BG GrowUp Job Bot",
        "keywords": ["job result today", "exam result 2026", "recruitment news"],
        "competitors": [],
    },
    "history-facts-bot": {
        "label": "Hindi History Facts",
        "keywords": ["history facts hindi", "itihas rochak tathya", "world history hindi"],
        "competitors": [],
    },
    "reels-bot": {
        "label": "BG Reels Bot",
        "keywords": ["trending reel product", "viral gadget shorts", "amazon finds shorts"],
        "competitors": [],
    },
}

HISTORY_FILE = "history.json"
TOP_N = 5
RECENCY_DAYS = 3  # kitne purane videos tak consider karna hai

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # optional

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ---------------------------------------------------------------------
# 1) TREND FETCHING (multi-source)
# ---------------------------------------------------------------------

def fetch_youtube_trending(keyword, limit=10):
    """yt-dlp ke through YouTube search results nikalna — koi API key nahi."""
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{limit}:{keyword}",
            "--dump-json",
            "--no-warnings",
            "--skip-download",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "title": data.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={data.get('id')}",
                    "views": data.get("view_count") or 0,
                    "upload_date": data.get("upload_date"),  # YYYYMMDD
                    "source": "youtube",
                })
            except json.JSONDecodeError:
                continue
        return videos
    except Exception as e:
        print(f"[youtube] error for '{keyword}': {e}")
        return []


def fetch_reddit_trending(keyword, limit=10):
    """Reddit ka public search JSON endpoint — auth ki zaroorat nahi."""
    try:
        url = f"https://www.reddit.com/search.json?q={keyword}&sort=hot&limit={limit}"
        headers = {"User-Agent": "trending-finder-bot/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            posts.append({
                "title": d.get("title", ""),
                "url": "https://reddit.com" + d.get("permalink", ""),
                "views": d.get("ups", 0),
                "upload_date": datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc
                ).strftime("%Y%m%d"),
                "source": "reddit",
            })
        return posts
    except Exception as e:
        print(f"[reddit] error for '{keyword}': {e}")
        return []


def fetch_google_trends_related(keyword):
    """
    Google Trends ka unofficial 'related queries' endpoint scrape karna.
    Koi key nahi chahiye, lekin ye endpoint kabhi-kabhi format badal deta
    hai — isliye try/except ke saath best-effort hai.
    """
    try:
        url = (
            "https://trends.google.com/trends/api/dailytrends"
            "?hl=hi-IN&tz=-330&geo=IN"
        )
        resp = requests.get(url, timeout=15)
        raw = resp.text.replace(")]}',", "", 1)
        data = json.loads(raw)
        trends = []
        for day in data.get("default", {}).get("trendingSearchesDays", []):
            for item in day.get("trendingSearches", []):
                title = item.get("title", {}).get("query", "")
                if keyword.split()[0].lower() in title.lower():
                    trends.append({
                        "title": title,
                        "url": f"https://www.google.com/search?q={title.replace(' ', '+')}",
                        "views": item.get("formattedTraffic", "0"),
                        "upload_date": datetime.now(timezone.utc).strftime("%Y%m%d"),
                        "source": "google_trends",
                    })
        return trends
    except Exception as e:
        print(f"[google_trends] error: {e}")
        return []


def fetch_all_sources(keywords):
    combined = []
    for kw in keywords:
        combined += fetch_youtube_trending(kw)
        combined += fetch_reddit_trending(kw)
    # Google Trends sirf ek baar per channel (rate-limit friendly)
    combined += fetch_google_trends_related(keywords[0])
    return combined


# ---------------------------------------------------------------------
# 2) FILTERING — recency + duplicate removal
# ---------------------------------------------------------------------

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def is_recent(upload_date_str, days=RECENCY_DAYS):
    if not upload_date_str:
        return True  # date na mile to reject mat karo
    try:
        d = datetime.strptime(upload_date_str, "%Y%m%d")
        return d >= datetime.now() - timedelta(days=days)
    except Exception:
        return True


def dedupe_and_filter(topics, used_titles):
    seen = set()
    filtered = []
    for t in topics:
        title_key = t["title"].strip().lower()
        if title_key in seen or title_key in used_titles:
            continue
        if not is_recent(t.get("upload_date")):
            continue
        seen.add(title_key)
        filtered.append(t)
    return filtered


# ---------------------------------------------------------------------
# 3) SCORING — heuristic (default) + optional Gemini boost
# ---------------------------------------------------------------------

def heuristic_score(topic):
    views = topic.get("views", 0)
    try:
        views = float(str(views).replace("K", "e3").replace("M", "e6")
                       .replace("+", "").replace(",", "") or 0)
        views = eval(views) if isinstance(views, str) else views
    except Exception:
        views = 0
    recency_bonus = 1.5 if topic.get("source") == "google_trends" else 1.0
    return views * recency_bonus


def gemini_score(topic, niche_label):
    """Optional: agar GEMINI_API_KEY set hai to har topic ko 0-10 score de."""
    if not GEMINI_API_KEY:
        return None
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        )
        prompt = (
            f"Channel niche: {niche_label}\n"
            f"Video topic: {topic['title']}\n"
            "Is topic ka viral potential 0 se 10 ke beech ek number mein "
            "batao. Sirf number likho, kuch aur nahi."
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, json=payload, timeout=20)
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return float("".join(c for c in text if c.isdigit() or c == "."))
    except Exception as e:
        print(f"[gemini] scoring skipped: {e}")
        return None


def rank_topics(topics, niche_label):
    for t in topics:
        h = heuristic_score(t)
        g = gemini_score(t, niche_label)
        t["score"] = (h / 1000.0) + (g or 0) * 100  # dono scale ko mila diya
    topics.sort(key=lambda x: x["score"], reverse=True)
    return topics[:TOP_N]


# ---------------------------------------------------------------------
# 4) COMPETITOR WATCH
# ---------------------------------------------------------------------

def fetch_competitor_latest(channel_url, limit=3):
    try:
        cmd = [
            "yt-dlp", channel_url, "--flat-playlist", "--dump-json",
            "--playlist-end", str(limit), "--no-warnings",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            data = json.loads(line)
            videos.append({
                "title": data.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={data.get('id')}",
            })
        return videos
    except Exception as e:
        print(f"[competitor] error: {e}")
        return []


# ---------------------------------------------------------------------
# 5) PERFORMANCE FEEDBACK LOOP
# ---------------------------------------------------------------------

def track_uploaded_video_performance(video_url):
    """Purani uploaded video ke current views nikalna (public page se)."""
    try:
        cmd = ["yt-dlp", video_url, "--dump-json", "--no-warnings", "--skip-download"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout.strip())
        return data.get("view_count", 0)
    except Exception:
        return None


def update_performance_log(history):
    """History mein saved purani uploaded videos ke views refresh karna,
    taaki pata chale kaunsi category best chal rahi hai."""
    for channel, entries in history.items():
        for entry in entries.get("uploaded", []):
            views = track_uploaded_video_performance(entry["url"])
            if views is not None:
                entry["latest_views"] = views
    return history


def best_performing_category(history):
    """Feedback loop: sabse zyada views wali category dhoondo taaki
    agli baar usko priority mil sake."""
    scores = {}
    for channel, entries in history.items():
        total = sum(e.get("latest_views", 0) for e in entries.get("uploaded", []))
        scores[channel] = total
    if not scores:
        return None
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------
# 6) TELEGRAM MESSAGING
# ---------------------------------------------------------------------

def send_telegram_message(text, reply_markup=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}/sendMessage", data=payload, timeout=15)


def build_topic_keyboard(channel_key, topics):
    buttons = []
    for i, t in enumerate(topics):
        buttons.append([
            {"text": "✅ Use", "callback_data": f"use|{channel_key}|{i}"},
            {"text": "❌ Skip", "callback_data": f"skip|{channel_key}|{i}"},
        ])
    return {"inline_keyboard": buttons}


def format_channel_message(channel_key, label, topics):
    lines = [f"<b>📺 {label}</b> — Top {len(topics)} Trending Topics\n"]
    for i, t in enumerate(topics, 1):
        lines.append(f"{i}. {t['title']}\n   🔗 {t['url']}  (source: {t['source']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    history = load_history()

    for channel_key, cfg in CHANNELS.items():
        used_titles = {
            e["title"].strip().lower()
            for e in history.get(channel_key, {}).get("suggested", [])
        }

        raw_topics = fetch_all_sources(cfg["keywords"])
        filtered = dedupe_and_filter(raw_topics, used_titles)
        top_topics = rank_topics(filtered, cfg["label"])

        if not top_topics:
            send_telegram_message(f"⚠️ {cfg['label']}: aaj koi naya trending topic nahi mila.")
            continue

        # Competitor watch
        for comp_url in cfg.get("competitors", []):
            latest = fetch_competitor_latest(comp_url)
            if latest:
                comp_text = "\n".join(f"- {v['title']}" for v in latest)
                send_telegram_message(f"👀 Competitor update ({cfg['label']}):\n{comp_text}")

        # Send main list with inline buttons
        msg = format_channel_message(channel_key, cfg["label"], top_topics)
        keyboard = build_topic_keyboard(channel_key, top_topics)
        send_telegram_message(msg, keyboard)

        # Save to history so it's not repeated tomorrow
        history.setdefault(channel_key, {"suggested": [], "uploaded": []})
        history[channel_key]["suggested"].extend(top_topics)
        # last 200 tak hi rakho, warna file badi ho jayegi
        history[channel_key]["suggested"] = history[channel_key]["suggested"][-200:]

        time.sleep(2)  # Telegram rate-limit se bachne ke liye

    # Feedback loop — purani videos ke views refresh
    history = update_performance_log(history)
    best = best_performing_category(history)
    if best:
        send_telegram_message(f"📊 Feedback: abhi tak sabse zyada views <b>{CHANNELS[best]['label']}</b> ki videos par aa rahe hain.")

    save_history(history)


if __name__ == "__main__":
    main()
