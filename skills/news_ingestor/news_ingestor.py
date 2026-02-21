import os
import sys
import time
import csv
import json
import traceback
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

# Config (PUBLIC REPO: use generic placeholders only)
FEEDS = [
    ("Placeholder Feed 1", "https://example.com/feed1.xml"),
    ("Placeholder Feed 2", "https://example.com/feed2.xml"),
]
WEBSITES = [
    "https://example.com",
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
MAX_PER_FEED = 3
MAX_TOTAL_ARTICLES = 60

HEADERS = {"User-Agent": "NanobotNews/1.0 (+https://example.com)"}


def requests_get_with_retries(url, headers=None, timeout=5, max_retries=3, backoff=1.0):
    headers = headers or HEADERS
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            # small delay to be polite
            time.sleep(0.5)
            return r
        except requests.exceptions.RequestException:
            if attempt == max_retries:
                return None
            time.sleep(backoff * attempt)
    return None


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


def fetch_article_text(url, max_chars=4000):
    if not url:
        return ""
    r = requests_get_with_retries(url, headers=HEADERS, timeout=10, max_retries=3, backoff=1.0)
    if not r:
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
        # Fallback: largest cluster of paragraphs
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


def summarize_text(text, max_sentences=3, max_chars=400):
    if not text:
        return ""
    # simple sentence splitter
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    sel = []
    total = 0
    for s in sents:
        s = s.replace('\n', ' ').strip()
        if not s:
            continue
        sel.append(s)
        total += len(s)
        if len(sel) >= max_sentences or total >= max_chars:
            break
    return ' '.join(sel)[:max_chars]


def scrape_homepage_for_links(site, max_links=10):
    links = []
    r = requests_get_with_retries(site, headers=HEADERS, timeout=10, max_retries=3, backoff=1.0)
    if not r:
        return []
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not href:
                continue
            # normalize
            if href.startswith("/"):
                href = site.rstrip("/") + href
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
    lines = []
    for i, a in enumerate(articles[:20], start=1):
        title = a.get('title')
        src = a.get('source') or a.get('source_name')
        link = a.get('link')
        snippet = a.get('summary') or a.get('snippet') or ""
        lines.append(f"{i}. {title} ({src})\n{snippet}\n{link}\n")
    return "\n".join(lines)


def save_raw_and_summary(timestamp, articles, out_base_name):
    RAW_DIR = os.path.join(os.path.dirname(__file__), 'data', 'raw_items')
    os.makedirs(RAW_DIR, exist_ok=True)
    saved_files = []
    for a in articles:
        fid = a.get('link') or a.get('title')
        safe = ''.join([c if c.isalnum() or c in ['-','_'] else '_' for c in (fid or '')])[:120]
        fname = f"rss_{safe}.json"
        payload = {
            'title': a.get('title'),
            'link': a.get('link'),
            'summary': a.get('summary'),
            'source': a.get('source'),
            'fetched_at': timestamp
        }
        try:
            with open(os.path.join(RAW_DIR, fname), 'w', encoding='utf8') as rf:
                json.dump(payload, rf, ensure_ascii=False, indent=2)
            saved_files.append(os.path.join(RAW_DIR, fname))
        except Exception:
            pass
    return saved_files


def save_markdown(timestamp, summary_text, articles, out_base_name):
    filename = f"Latest_News_{out_base_name}.md"
    filepath = os.path.join(MEMORY_DIR, filename)
    with open(filepath, "w", encoding="utf8") as f:
        f.write(f"# Latest News - {timestamp}\n\n")
        f.write(summary_text)
        f.write("\n\n---\n\n")
        f.write("## Articles (raw)\n\n")
        for a in articles:
            f.write(f"- {a.get('title')} | {a.get('link')} | {a.get('source')}\n")
    csv_name = f"Latest_News_{out_base_name}.csv"
    csv_path = os.path.join(MEDIA_DIR, csv_name)
    with open(csv_path, "w", newline='', encoding="utf8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["title", "link", "source", "summary"])
        for a in articles:
            writer.writerow([a.get('title', ''), a.get('link', ''), a.get('source', ''), a.get('summary', '')])
    return filepath, csv_path


def append_memory_index(timestamp, md_path, csv_path):
    memfile = os.path.join(MEMORY_DIR, "MEMORY.md")
    entry = f"\n- [Latest News]({md_path}) - {timestamp} (CSV: {csv_path})"
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
                full = fetch_article_text(link, max_chars=2000)
                summary = summarize_text(full, max_sentences=3, max_chars=400)
                articles.append({"title": e.get('title'), "link": link, "source_name": name, "source": url, "summary": summary})
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
                    full = fetch_article_text(link, max_chars=2000)
                    summary = summarize_text(full, max_sentences=3, max_chars=400)
                    articles.append({"title": l.get('title') or link, "link": link, "source_name": site, "source": site, "summary": summary})
                    if len(articles) >= MAX_TOTAL_ARTICLES:
                        break
            except Exception:
                continue
            if len(articles) >= MAX_TOTAL_ARTICLES:
                break

    # Save raw items and summaries
    saved = save_raw_and_summary(timestamp, articles, now.strftime("%Y%m%d_%H%M"))

    # Prepare summary document
    summary_text = make_summary(articles)
    out_base = now.strftime("%Y%m%d_%H%M")
    md_path, csv_path = save_markdown(timestamp, summary_text, articles, out_base)
    append_memory_index(timestamp, md_path, csv_path)

    # Send a short Telegram message
    token = os.environ.get("NANOBOT_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        chat_id = os.environ.get("NANOBOT_TELEGRAM_CHAT_ID")
    if token and chat_id:
        short = f"Nanobot: Latest News ({timestamp})\nTop items:\n"
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
