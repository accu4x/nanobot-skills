"""
self-improvement/indexer.py
Simple FAISS-based indexer. Requires 'faiss' and 'sentence-transformers' if used.
This module is optional — the ingest runner imports it only if index_on is true.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / 'data' / 'faiss_index'
INDEX_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = INDEX_DIR / 'index.faiss'
META_FILE = INDEX_DIR / 'meta.json'

# lazy imports
def ensure_dependencies():
    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise RuntimeError('Missing dependencies for indexer: faiss and sentence-transformers')


def add_documents(docs: List[Dict[str, Any]]):
    """Add documents to the FAISS index. Each doc: {'id': str, 'text': str}
    This is a simple append; no de-duplication.
    """
    ensure_dependencies()
    from sentence_transformers import SentenceTransformer
    import faiss
    import json
    model = SentenceTransformer('all-MiniLM-L6-v2')
    texts = [d.get('text','') for d in docs]
    ids = [d.get('id') for d in docs]
    vecs = model.encode(texts, convert_to_numpy=True)
    dim = vecs.shape[1]
    # load or create index
    if INDEX_FILE.exists():
        idx = faiss.read_index(str(INDEX_FILE))
    else:
        idx = faiss.IndexFlatL2(dim)
    idx.add(vecs)
    faiss.write_index(idx, str(INDEX_FILE))
    # append metadata
    meta = []
    if META_FILE.exists():
        meta = json.loads(META_FILE.read_text(encoding='utf-8') or '[]')
    for i, _id in enumerate(ids):
        meta.append({'id': _id, 'text_len': len(texts[i])})
    META_FILE.write_text(json.dumps(meta, indent=2), encoding='utf-8')


def search(query: str, k: int = 5):
    ensure_dependencies()
    from sentence_transformers import SentenceTransformer
    import faiss
    import numpy as np
    model = SentenceTransformer('all-MiniLM-L6-v2')
    qvec = model.encode([query], convert_to_numpy=True)
    if not INDEX_FILE.exists():
        return []
    idx = faiss.read_index(str(INDEX_FILE))
    D, I = idx.search(qvec, k)
    meta = json.loads(META_FILE.read_text(encoding='utf-8') or '[]')
    results = []
    for dist, i in zip(D[0], I[0]):
        if i < 0 or i >= len(meta):
            continue
        results.append({'meta': meta[i], 'distance': float(dist)})
    return results
