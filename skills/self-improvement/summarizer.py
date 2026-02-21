"""
self-improvement/summarizer.py
Utility to convert a Moltbook post dict into a concise summary and high-signal ideas.
This is intentionally simple and model-free: uses heuristic extraction and basic trimming.
"""
from __future__ import annotations
from typing import Dict, Any


def summarize_post(post: Dict[str, Any]) -> Dict[str, Any]:
    title = post.get('title') or post.get('headline') or post.get('name') or ''
    body = post.get('body') or post.get('content') or post.get('text') or ''
    # naive highlight extraction: split into sentences and pick top 3 longest unique lines
    lines = [l.strip() for l in body.replace('\r','').split('\n') if l.strip()]
    lines_sorted = sorted(lines, key=lambda s: -len(s))
    highlights = []
    for l in lines_sorted:
        if len(highlights) >= 3:
            break
        if l not in highlights:
            highlights.append(l)
    if not highlights and title:
        highlights = [title]
    sample = highlights[0] if highlights else (body[:200] if body else '')
    return {
        'title': title,
        'body': body,
        'highlights': highlights,
        'sample_quote': sample
    }
