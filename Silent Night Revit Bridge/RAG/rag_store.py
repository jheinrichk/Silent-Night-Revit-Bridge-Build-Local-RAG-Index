# -*- coding: utf-8 -*-
"""
Local Revit Bridge RAG store.
No external dependencies. Uses lexical scoring over chunked text and bridge cycle records.
Place this folder at C:\RevitBridge\RAG, then run rag_ingest.py whenever corpus files change.
"""
from __future__ import print_function
import argparse
import json
import math
import os
import re
import time
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = RAG_ROOT / "corpus"
CYCLES_DIR = RAG_ROOT / "cycles"
STORE_DIR = RAG_ROOT / "vector_store"
INDEX_FILE = STORE_DIR / "index.jsonl"
META_FILE = STORE_DIR / "meta.json"
CYCLE_LOG = CYCLES_DIR / "bridge_cycles.jsonl"

TEXT_EXTS = {".txt", ".md", ".py", ".json", ".csv", ".log"}
STOPWORDS = set("""
a an and are as at be by for from has have if in into is it its no not of on or that the this to with you your
use using used when where which while will should must do does did done can could would may might before after
def class import from try except true false none self
""".split())


def ensure_dirs():
    for d in [CORPUS_DIR, CYCLES_DIR, STORE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def tokenize(text):
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[0-9]+", text or "")
    out = []
    for w in words:
        lw = w.lower()
        if lw not in STOPWORDS and len(lw) > 1:
            out.append(lw)
    return out


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        try:
            return Path(path).read_text(errors="replace")
        except Exception:
            return ""


def chunk_text(text, max_chars=2400, overlap=300):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        if end < n:
            cut = text.rfind("\n\n", start, end)
            if cut > start + max_chars // 2:
                end = cut
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
        if end >= n:
            break
        start = max(0, end - overlap)
    return parts


def iter_corpus_files():
    ensure_dirs()
    for root, dirs, files in os.walk(str(CORPUS_DIR)):
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() in TEXT_EXTS:
                yield p


def iter_cycle_records(limit=500):
    if not CYCLE_LOG.exists():
        return
    try:
        lines = CYCLE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []
    for line in lines[-limit:]:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        title = "bridge_cycle_{}".format(rec.get("cycle_number", "unknown"))
        state = rec.get("next_recommended_state", "UNKNOWN")
        body = "STATE: {}\nCODE:\n{}\nRPS_OUTPUT:\n{}".format(state, rec.get("code_preview", ""), rec.get("rps_output_preview", ""))
        yield title, body


def build_index(include_cycles=True):
    ensure_dirs()
    docs = []
    for p in iter_corpus_files():
        txt = read_text(p)
        for i, ch in enumerate(chunk_text(txt)):
            toks = tokenize(ch)
            docs.append({
                "source": str(p),
                "title": p.name,
                "chunk": i,
                "text": ch,
                "tokens": toks,
                "kind": "corpus"
            })
    if include_cycles:
        for title, body in iter_cycle_records():
            for i, ch in enumerate(chunk_text(body, max_chars=2600, overlap=250)):
                toks = tokenize(ch)
                docs.append({
                    "source": str(CYCLE_LOG),
                    "title": title,
                    "chunk": i,
                    "text": ch,
                    "tokens": toks,
                    "kind": "cycle"
                })
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1
    n_docs = max(1, len(docs))
    with INDEX_FILE.open("w", encoding="utf-8") as f:
        for d in docs:
            tf = {}
            for t in d["tokens"]:
                tf[t] = tf.get(t, 0) + 1
            d2 = dict(d)
            d2["tf"] = tf
            d2.pop("tokens", None)
            f.write(json.dumps(d2, ensure_ascii=False) + "\n")
    META_FILE.write_text(json.dumps({"updated": time.time(), "doc_count": n_docs, "df": df}, indent=2), encoding="utf-8")
    return n_docs


def load_index():
    ensure_dirs()
    if not INDEX_FILE.exists() or not META_FILE.exists():
        build_index(include_cycles=True)
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        meta = {"doc_count": 1, "df": {}}
    docs = []
    try:
        for line in INDEX_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                docs.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return meta, docs


def score_doc(q_tokens, doc, meta):
    if not q_tokens:
        return 0.0
    tf = doc.get("tf", {})
    df = meta.get("df", {}) or {}
    n_docs = float(max(1, meta.get("doc_count", 1)))
    score = 0.0
    for t in q_tokens:
        if t in tf:
            idf = math.log((n_docs + 1.0) / (float(df.get(t, 0)) + 1.0)) + 1.0
            score += (1.0 + math.log(float(tf[t]))) * idf
    # Favor prior bridge cycles lightly because they capture this exact environment.
    if doc.get("kind") == "cycle":
        score *= 1.12
    return score


def retrieve(query, top_k=8, max_chars=6000):
    meta, docs = load_index()
    q_tokens = tokenize(query)
    ranked = []
    for d in docs:
        sc = score_doc(q_tokens, d, meta)
        if sc > 0:
            ranked.append((sc, d))
    ranked.sort(key=lambda x: x[0], reverse=True)
    chunks = []
    total = 0
    for sc, d in ranked[:max(1, int(top_k))]:
        header = "[RAG source={0} chunk={1} score={2:.2f}]".format(d.get("title"), d.get("chunk"), sc)
        txt = header + "\n" + d.get("text", "").strip()
        if total + len(txt) > max_chars:
            txt = txt[:max(0, max_chars - total)]
        if txt.strip():
            chunks.append(txt)
            total += len(txt) + 2
        if total >= max_chars:
            break
    return "\n\n---\n\n".join(chunks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--max-chars", type=int, default=6000)
    args = ap.parse_args()
    if args.build:
        n = build_index(include_cycles=True)
        print("INDEX_BUILT doc_count={}".format(n))
        return
    if args.query:
        print(retrieve(args.query, top_k=args.top_k, max_chars=args.max_chars))
        return
    print("Use --build or --query")


if __name__ == "__main__":
    main()
