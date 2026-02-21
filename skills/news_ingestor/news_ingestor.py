import os
import sys
import time
import csv
import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

# Config
FEEDS = [
    ("Hockey Writers", "https://thehockeywriters.com/feed/"),
    ("GTS", "https://gogts.net/sports/hockey/feed/"),
    ("Spectors Hockey", "https://www.spectorshockey.net/feed/"),
    ("Gong Show", "https://www.hockeycardsgongshow.com/blog-feed.xml"),
    ("The Hockey News", "https://thehockeynews.com/rss/THNHOME/full"),
    ("The Win Column", "https://thewincolumn.ca/feed/"),
    ("NHL Rumors", "https://nhlrumors.com/feed/"),
    ("Upper Deck", "https://upperdeck.com/category/hockey/feed/"),
    ("NHL Trade Talks", "https://nhltradetalk.com/feed/"),
    ("90s Hockey Feed", "https://www.90shockeycardhistory.com/blog-feed.xml"),
    ("Hockey Writers Collecting", "https://thehockeywriters.com/category/collecting-hockey/feed/")
]
WEBSITES = [
    "https://www.thehockeynews.com",
    "https://www.espn.com/nhl",
    "https://www.tsn.ca/nhl",
    "https://www.beckett.com/news/category/hockey-news-categories/"
]

# Paths - use user-friendly home path
WORKSPACE = os.path.join(os.path.expanduser("~"), ".nanobot", "workspace")
MEDIA_DIR = os.path.join(WORKSPACE, "media")
MEMORY_DIR = os.path.join(WORKSPACE, "memory")
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR, exist_ok=True)
if not os.path.exists(MEMORY_DIR):
    os.makedirs(MEMORY_DIR, exist_ok=True)

TIMESTAMP_TZ = "America/New_York"

# Limits
MAX_PER_FEED = 5
MAX_TOTAL_ARTICLES = 60

HEADERS = {"User-Agent": "HobbyHeroBot/1.0 (+https://example.com)"}


def fetch_rss(feed_url, max_items=5):
    try:
        d = feedparser.parse(feed_url)
    except Exception:
        return []
    items = []
    for e in d.entries[:max_items]:
        title = e.get("title") or "(no title)"
        link = e.get("link") or e.get("id") or None
        published = e.get("published") or e.get("updated") or None
        items.append({"title": title, "link": link, "published": published, "source": feed_url})
    return items


def fetch_article_text(url, max_chars=2000):
    if not url:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception:
        return ""
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        # Try common article containers
        article = soup.find("article")
        if article:
            text = "\n\n".join([p.get_text(strip=True) for p in article.find_all("p")])
            if text:
                return text[:max_chars]
        # Fallback: main tag
        main = soup.find("main")
        if main:
            text = "\n\n".join([p.get_text(strip=True) for p in main.find_all("p")])
            if text:
                return text[:max_chars]
        # Fallback: largest div or body paragraphs
        ps = soup.find_all("p")
        if ps:
            texts = []
            total = 0
            for p in ps:
                t = p.get_text(strip=True)
                if not t:
                    continue
                texts.append(t)
                total += len(t)
                if total > max_chars:
                    break
            return "\n\n".join(texts)[:max_chars]
    except Exception:
        return ""
    return ""


def scrape_homepage_for_links(site, max_links=10):
    links = []
    try:
        r = requests.get(site, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not href:
                continue
            # normalize
            if href.startswith("/"):
                href = site.rstrip("/") + href
            if site.split("//")[-1] in href or any(k in href.lower() for k in ("nhl","hockey","card")):
                links.append((text or href, href))
            if len(links) >= max_links:
                break
    except Exception:
        pass
    # dedupe preserving order
    seen = set()
    out = []
    for t, h in links:
        if h in seen:
            continue
        seen.add(h)
        out.append({"title": t, "link": h})
    return out


def make_summary(articles):
    # articles: list of dicts {title, link, source, snippet}
    lines = []
    for i, a in enumerate(articles[:20], start=1):
        title = a.get("title")
        src = a.get("source") or a.get("source_name")
        link = a.get("link")
        snippet = a.get("snippet") or ""
        lines.append(f"{i}. {title} ({src})\n{snippet}\n{link}\n")
    return "\n".join(lines)


def save_markdown(timestamp, summary_text, articles, out_base_name):
    # Save into memory and media
    filename = f"Latest_Hockey_Card_News_{out_base_name}.md"
    filepath = os.path.join(MEMORY_DIR, filename)
    with open(filepath, "w", encoding="utf8") as f:
        f.write(f"# Latest Hockey/Card News - {timestamp}\n\n")
        f.write(summary_text)
        f.write("\n\n---\n\n")
        f.write("## Articles (raw)\n\n")
        for a in articles:
            f.write(f"- {a.get('title')} | {a.get('link')} | {a.get('source')}\n")
    # CSV
    csv_name = f"Latest_Hockey_Card_News_{out_base_name}.csv"
    csv_path = os.path.join(MEDIA_DIR, csv_name)
    with open(csv_path, "w", newline='', encoding="utf8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["title","link","source","snippet"]) 
        for a in articles:
            writer.writerow([a.get('title',''), a.get('link',''), a.get('source',''), a.get('snippet','')])
    return filepath, csv_path


def append_memory_index(timestamp, md_path, csv_path):
    memfile = os.path.join(MEMORY_DIR, "MEMORY.md")
    entry = f"\n- [Latest Hockey/Card News]({md_path}) - {timestamp} (CSV: {csv_path})"
    try:
        if not os.path.exists(memfile):
            with open(memfile, "w", encoding="utf8") as f:
                f.write("# Memory\n\n")
                f.write(entry)
        else:
            with open(memfile, "a", encoding="utf8") as f:
                f.write(entry)
    except Exception:
        pass


def save_raw_and_summary(timestamp, summary_text, articles, out_base_name):
    """Save the markdown summary and CSV, index into memory, and return paths and base name."""
    try:
        md_path, csv_path = save_markdown(timestamp, summary_text, articles, out_base_name)
        append_memory_index(timestamp, md_path, csv_path)
        return md_path, csv_path, out_base_name
    except Exception:
        return None, None, out_base_name


def send_telegram_summary(token, chat_id, text):
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        r = requests.post(url, data=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def main():
    try:
        tz = ZoneInfo(TIMESTAMP_TZ)
    except Exception:
        tz = None
    now = datetime.now(tz) if tz else datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%d %H:%M %Z")
    articles = []
    seen_links = set()

    # Fetch RSS feeds
    for name, url in FEEDS:
        try:
            entries = fetch_rss(url, max_items=MAX_PER_FEED)
            for e in entries:
                link = e.get('link')
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                snippet = fetch_article_text(link, max_chars=400)
                articles.append({"title": e.get('title'), "link": link, "source_name": name, "source": url, "snippet": snippet})
                if len(articles) >= MAX_TOTAL_ARTICLES:
                    break
        except Exception:
            continue
        if len(articles) >= MAX_TOTAL_ARTICLES:
            break

    # Scrape websites for additional links
    if len(articles) < MAX_TOTAL_ARTICLES:
        for site in WEBSITES:
            try:
                links = scrape_homepage_for_links(site, max_links=6)
                for l in links:
                    link = l.get('link')
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    snippet = fetch_article_text(link, max_chars=400)
                    articles.append({"title": l.get('title') or link, "link": link, "source_name": site, "source": site, "snippet": snippet})
                    if len(articles) >= MAX_TOTAL_ARTICLES:
                        break
            except Exception:
                continue
            if len(articles) >= MAX_TOTAL_ARTICLES:
                break

    # Save raw items to data/raw_items
    RAW_DIR = os.path.join(os.path.dirname(__file__), 'data', 'raw_items')
    os.makedirs(RAW_DIR, exist_ok=True)
    for a in articles:
        # craft a safe filename from link or title
        fid = a.get('link') or a.get('title')
        safe = ''.join([c if c.isalnum() or c in ['-','_'] else '_' for c in (fid or '')])[:120]
        fname = f"rss_{safe}.json"
        try:
            raw_obj = {
                'id': safe,
                'source': 'rss',
                'source_name': a.get('source_name') or a.get('source'),
                'url': a.get('link'),
                'title': a.get('title'),
                'body': a.get('snippet') or '',
                'fetched_at': timestamp,
                'metadata': {'origin_feed': a.get('source')}
            }
            with open(os.path.join(RAW_DIR, fname), 'w', encoding='utf8') as rf:
                json.dump(raw_obj, rf, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Prepare summary
    summary_text = make_summary(articles)
    out_base = now.strftime("%Y%m%d_%H%M")
    md_path, csv_path = save_markdown(timestamp, summary_text, articles, out_base)
    append_memory_index(timestamp, md_path, csv_path)

    # Send a short Telegram message
    token = os.environ.get("NANOBOT_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    # fallback: use known chat id if available in env or hardcoded (optional)
    if not chat_id:
        chat_id = os.environ.get("NANOBOT_TELEGRAM_CHAT_ID")
    if token and chat_id:
        short = f"HobbyHero: Latest Hockey/Card News ({timestamp})\nTop items:\n"
        for i, a in enumerate(articles[:5], start=1):
            short += f"{i}. {a.get('title')}\n"
        short += f"\nSaved: {os.path.basename(md_path)}"
        send_telegram_summary(token, chat_id, short)

    print("Done. Saved:", md_path, csv_path)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        sys.exit(1)
