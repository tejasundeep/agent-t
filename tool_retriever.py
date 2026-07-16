"""Tool Retriever — semantic + BM25 hybrid retrieval for the tool registry.

Keeps the LLM's context window lean by selecting only the top-K most relevant
tool schemas for each query, using:
  - Layer 1: Exact name / keyword hit (instant)
  - Layer 2: BM25 keyword scoring (milliseconds, no ML)
  - Layer 3: Semantic cosine similarity via LM Studio embeddings API

Falls back to returning the full schema list if LM Studio is unreachable.
"""
import hashlib
import json
import math
import pathlib
import re
import threading
from typing import Optional

import requests

# ── Config ────────────────────────────────────────────────────────────────────
LM_STUDIO_BASE   = "http://localhost:1234/v1"
EMBED_MODEL      = "text-embedding-embeddinggemma-300m-qat"
EMBED_TIMEOUT    = 8          # seconds per embedding call
TOP_K            = 14         # max tools passed to LLM per query
SEMANTIC_WEIGHT  = 0.70       # fraction of score from embeddings
BM25_WEIGHT      = 0.30       # fraction of score from BM25

# Always include these in every call regardless of relevance score
PINNED_TOOLS = {
    "python_interpreter", "create_plan", "update_task",
    "add_plan_note", "check_resume",
    "create_tool", "upgrade_tool", "read_tool_source",
}

CACHE_FILE = pathlib.Path(__file__).parent / ".tool_embed_cache.json"

# BM25 stopwords — stripped before scoring
_STOPWORDS = {
    "a", "an", "the", "is", "in", "on", "to", "of", "for", "and",
    "or", "with", "use", "using", "used", "when", "you", "your",
    "this", "that", "it", "as", "from", "by", "be", "are", "at",
}


# ── BM25 helpers ──────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _bm25(query_tokens: list[str], doc_tokens: list[str],
          k1: float = 1.5, b: float = 0.75, avg_dl: float = 20.0) -> float:
    """Simplified BM25 score (no IDF — single-doc, so IDF is constant)."""
    dl = len(doc_tokens)
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    score = 0.0
    for qt in query_tokens:
        tf = tf_map.get(qt, 0)
        score += (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
    return score


# ── Cosine similarity (pure Python, no numpy required) ───────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


# ── Retriever ─────────────────────────────────────────────────────────────────
class ToolRetriever:
    """Semantic + BM25 hybrid retriever for tool schemas."""

    def __init__(self):
        self._lock   = threading.RLock()
        # name -> {"desc": str, "desc_hash": str, "embedding": list[float] | None, "schema": dict}
        self._index: dict[str, dict] = {}
        self._lm_available = True   # flipped to False on first timeout/error
        self._load_cache()

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[list[float]]:
        """Call LM Studio /v1/embeddings. Returns None if unavailable."""
        if not self._lm_available:
            return None
        try:
            resp = requests.post(
                f"{LM_STUDIO_BASE}/embeddings",
                json={"model": EMBED_MODEL, "input": text},
                timeout=EMBED_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except requests.exceptions.ConnectionError:
            self._lm_available = False
            print("[ToolRetriever] LM Studio unreachable — falling back to BM25 only.")
            return None
        except Exception as e:
            print(f"[ToolRetriever] Embedding error: {e}")
            return None

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _desc_hash(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _save_cache(self):
        try:
            data = {
                name: {"desc": e["desc"], "desc_hash": e["desc_hash"], "embedding": e["embedding"]}
                for name, e in self._index.items()
                if e.get("embedding") is not None
            }
            CACHE_FILE.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        except Exception as e:
            print(f"[ToolRetriever] Cache save error: {e}")

    def _load_cache(self):
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                for name, entry in data.items():
                    self._index[name] = {
                        "desc": entry["desc"],
                        "desc_hash": entry["desc_hash"],
                        "embedding": entry["embedding"],
                        "schema": None,   # filled in when tool registers
                    }
                print(f"[ToolRetriever] Loaded {len(self._index)} embeddings from cache.")
        except Exception as e:
            print(f"[ToolRetriever] Cache load error: {e}")

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_tool(self, name: str, description: str, schema: dict):
        """Embed and store a tool. Called by the @tool decorator after registration.
        Uses cached embedding if description hasn't changed.
        """
        with self._lock:
            text = f"{name}: {description}"
            h    = self._desc_hash(text)
            existing = self._index.get(name, {})

            if existing.get("desc_hash") == h and existing.get("embedding") is not None:
                # Description unchanged — just refresh schema reference
                self._index[name]["schema"] = schema
                return

            # New or changed — re-embed
            embedding = self._embed(text)
            self._index[name] = {
                "desc": description,
                "desc_hash": h,
                "embedding": embedding,
                "schema": schema,
            }
            if embedding is not None:
                self._save_cache()

    def remove_tool(self, name: str):
        """Remove a tool from the index (called when a tool is deleted)."""
        with self._lock:
            if name in self._index:
                del self._index[name]
                self._save_cache()

    def reindex_all(self, all_schemas: list[dict]):
        """Sync the index against the current full schema list.
        Called once at startup after all tools are loaded.
        """
        schema_map = {s["function"]["name"]: s for s in all_schemas if s.get("function")}
        for name, schema in schema_map.items():
            desc = schema["function"].get("description", "")
            self.index_tool(name, desc, schema)

        # Remove stale entries no longer in the registry
        with self._lock:
            stale = [n for n in list(self._index) if n not in schema_map]
            for n in stale:
                del self._index[n]
            if stale:
                self._save_cache()

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def retrieve(self, query: str, all_schemas: list[dict]) -> list[dict]:
        """Return the top-K most relevant schemas for the query.

        Scoring:
          score = SEMANTIC_WEIGHT * cosine_sim + BM25_WEIGHT * normalised_bm25

        Pinned tools (planning, IaaT, tool management) are always included.
        Falls back to the full schema list if nothing is indexed yet.
        """
        with self._lock:
            if not self._index:
                return all_schemas     # cold start — nothing indexed yet

            schema_map: dict[str, dict] = {
                s["function"]["name"]: s
                for s in all_schemas if s.get("function")
            }

            query_tokens  = _tokenize(query)
            query_embed   = self._embed(query) if self._lm_available else None

            scores: dict[str, float] = {}
            for name, entry in self._index.items():
                if name not in schema_map:
                    continue

                # BM25
                doc_text   = f"{name} {entry['desc']}"
                doc_tokens = _tokenize(doc_text)
                bm25_raw   = _bm25(query_tokens, doc_tokens)
                # Normalise BM25 to ≈ [0, 1]  (cap at 10 raw score)
                bm25_norm  = min(bm25_raw / 10.0, 1.0)

                # Semantic
                sem = 0.0
                if query_embed and entry.get("embedding"):
                    sem = _cosine(query_embed, entry["embedding"])

                scores[name] = SEMANTIC_WEIGHT * sem + BM25_WEIGHT * bm25_norm

            # Sort by score descending
            ranked = sorted(scores, key=scores.__getitem__, reverse=True)

            # Take top-K, excluding pinned (added separately)
            selected = [n for n in ranked if n not in PINNED_TOOLS][:TOP_K]

            # Build result: top-K + all pinned that exist in registry
            result_names = list(selected)
            for pin in PINNED_TOOLS:
                if pin in schema_map and pin not in result_names:
                    result_names.append(pin)

            result = [schema_map[n] for n in result_names if n in schema_map]

            # Safety: if retrieval returned nothing, return everything
            if not result:
                return all_schemas

            return result


# ── Singleton ─────────────────────────────────────────────────────────────────
retriever = ToolRetriever()
