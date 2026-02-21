import os
import sys
import time
import csv
import json
import hashlib
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

# Config (repo/public copy should use placeholders; workspace copy may be populated)
FEEDS = [
    ("Example Feed", "https://example.com/feed.xml"),
]
WEBSITES = [
    "https://example.com/",
]

# Paths - prefer skill-local data; memory and workspace are optional external stores
SKILL_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(SKILL_DIR, 'data')
RAW_DIR = os.path.join(DATA_DIR, 'raw_items')
os.makedirs(RAW_DIR, exist_ok=True)

WORKSPACE = os.path.join(os.path.expanduser("~"), ".nanobot", "workspace")
MEDIA_DIR = os.path.join(WORKSPACE, "media")
MEMORY_DIR = os.path.join(WORKSPACE, "memory")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)

TIMESTAMP_TZ = "America/New_York"

# Limits
MAX_PER_FEED = 3
MAX_TOTAL_ARTICLES = 60

HEADERS = {"User-Agent": "nanobot-news-ingestor/1.0 (+https://example.com)"}

# Shared requests session
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _safe_filename_from_url(url, suffix=".json"):
    # Use a short hash plus basename to avoid leaking full URLs and keep filenames filesystem-safe
    h = hashlib.md5((url or "").encode('utf8')).hexdigest()[:12]
    parsed = urlparse(url or "")
    name = (parsed.path.rstrip('/').split('/')[-1] or parsed.netloc or 'item')[:60]
    safe = ''.join([c if c.isalnum() or c in ['-','_'] else '_' for c in name])
    return f"{h}_{safe}{suffix}"


def fetch_rss(feed_url, max_items=5):
    try:
        d = feedparser.parse(feed_url)
    except Exception:
        return []
    # feedparser may set .status or .bozo
    status = getattr(d, 'status', 200)
    if status and int(status) >= 400:
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
        r = SESSION.get(url, timeout=10)
        r.raise_for_status()
    except Exception:
        return ""
    text = ""
    # Try optional readability if available (prefer more accurate main-text extraction)
    try:
        from readability import Document
        doc = Document(r.text)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        text = "\n\n".join([p.get_text(strip=True) for p in soup.find_all('p')])
        if text:
            return text[:max_chars]
    except Exception:
        # readability not available or failed; continue with heuristics
        pass
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
        # Fallback: choose largest group of paragraphs by total length
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
        r = SESSION.get(site, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not href:
                continue
            # normalize
            href = urljoin(site, href)
            # crude filtering: same host or keywords
            hostname = urlparse(site).netloc.lower()
            if hostname in href or any(k in href.lower() for k in ("nhl", "hockey", "card", "news")):
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
        title = a.get("title") or "(no title)"
        src = a.get("source") or a.get("source_name") or ""
        link = a.get("link") or ""
        snippet = (a.get("snippet") or "").replace('\n', ' ')[:400]
        lines.append(f"{i}. {title} ({src})\n{snippet}\n{link}\n")
    return "\n".join(lines)


def save_markdown(timestamp, summary_text, articles, out_base_name):
    filename = f"Latest_News_{out_base_name}.md"
    filepath = os.path.join(MEMORY_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf8") as f:
            f.write(f"# Latest News - {timestamp}\n\n")
            f.write(summary_text)
            f.write("\n\n---\n\n")
            f.write("## Articles (raw)\n\n")
            for a in articles:
                f.write(f"- {a.get('title')} | {a.get('link')} | {a.get('source')}\n")
    except Exception:
        filepath = None
    # CSV
    csv_name = f"Latest_News_{out_base_name}.csv"
    csv_path = os.path.join(MEDIA_DIR, csv_name)
    try:
        with open(csv_path, "w", newline='', encoding="utf8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["title", "link", "source", "snippet"])
            for a in articles:
                writer.writerow([a.get('title', ''), a.get('link', ''), a.get('source', ''), a.get('snippet', '')])
    except Exception:
        csv_path = None
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


def save_raw_and_summary(timestamp, summary_text, articles, out_base_name):
    try:
        md_path, csv_path = save_markdown(timestamp, summary_text, articles, out_base_name)
        append_memory_index(timestamp, md_path, csv_path)
        return md_path, csv_path, out_base_name
    except Exception:
        return None, None, out_base_name


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

    # Prepare summary and save markdown + csv
    summary_text = make_summary(articles)
    out_base = now.strftime("%Y%m%d_%H%M")
    md_path, csv_path, saved_base = save_raw_and_summary(timestamp, summary_text, articles, out_base)

    # Additionally save per-article raw JSON into data/raw_items using safe filenames
    for a in articles:
        try:
            url = a.get('link') or a.get('title') or ''
            fname = _safe_filename_from_url(url)
            raw_obj = {
                'id': fname,
                'source': 'news_ingestor',
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
            # best-effort: do not fail the whole run for one save error
            continue

    # Send a short Telegram message if configured
    token = os.environ.get("NANOBOT_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("NANOBOT_TELEGRAM_CHAT_ID")
    if token and chat_id and md_path:
        short = f"Nanobot: Latest News ({timestamp})\nTop items:\n"
        for i, a in enumerate(articles[:5], start=1):
            short += f"{i}. {a.get('title')}\n"
        short += f"\nSaved: {os.path.basename(md_path)}"
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": short, "disable_web_page_preview": True}
            SESSION.post(url, data=payload, timeout=10)
        except Exception:
            pass

    print("Done. Saved:", md_path, csv_path)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
